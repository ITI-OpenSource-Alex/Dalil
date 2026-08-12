from typing import Any
from uuid import uuid4

import pytest

from app.services.writing_image_delivery_service import (
    S3WritingImageDeliveryService,
    WritingImageUnavailableError,
)


class FakeS3Client:
    """Fake S3 that actually tracks which objects exist.

    `missing_keys` is the whole point: the delivery service HEADs the object
    before pre-signing, because pre-signing never touches S3 and so would
    happily sign a URL against an empty bucket (BUG-022). A fake that reports
    everything present could not catch a regression of that guard.
    """

    def __init__(self, missing_keys: set[str] | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self.head_calls: list[str] = []
        self.missing_keys = missing_keys or set()

    def head_object(self, Bucket: str, Key: str) -> dict[str, Any]:  # noqa: N803
        self.head_calls.append(Key)
        if Key in self.missing_keys:
            raise RuntimeError(f"404 Not Found: {Key}")
        return {"ContentLength": 2048}

    def generate_presigned_url(self, operation: str, **kwargs: Any) -> str:
        self.calls.append({"operation": operation, **kwargs})
        key = kwargs["Params"]["Key"]
        return f"https://images.example/{key}?signature={len(self.calls)}"


IMAGE_KEY = "writing-images/IELTS-18/1/task1.png"


def test_missing_image_is_refused_rather_than_signed() -> None:
    """The BUG-022 scenario for a chart: the object is not in the bucket."""
    s3 = FakeS3Client(missing_keys={IMAGE_KEY})
    service = S3WritingImageDeliveryService(s3, "goa-writing-files")

    with pytest.raises(WritingImageUnavailableError) as exc:
        service.generate_image_url(IMAGE_KEY, uuid4())

    assert IMAGE_KEY in str(exc.value)
    # Nothing may be signed once the object is known missing.
    assert s3.calls == []


def test_object_is_head_checked_before_signing() -> None:
    s3 = FakeS3Client()
    service = S3WritingImageDeliveryService(s3, "goa-writing-files")

    service.generate_image_url(IMAGE_KEY, uuid4())

    assert s3.head_calls == [IMAGE_KEY]


def test_present_image_is_signed_with_7200_expiry_and_session_scope() -> None:
    s3 = FakeS3Client()
    service = S3WritingImageDeliveryService(s3, "goa-writing-files")
    session_id = uuid4()

    url = service.generate_image_url(IMAGE_KEY, session_id)

    assert url.startswith("https://images.example/")
    assert len(s3.calls) == 1
    call = s3.calls[0]
    assert call["operation"] == "get_object"
    assert call["Params"]["Bucket"] == "goa-writing-files"
    assert call["Params"]["Key"] == IMAGE_KEY
    assert call["ExpiresIn"] == 7200
    assert str(session_id) in call["Params"]["ResponseContentDisposition"]
    assert "inline" in call["Params"]["ResponseContentDisposition"]


def test_empty_key_raises_valueerror_not_unavailable() -> None:
    """A malformed (empty) key is a 500-class bug, distinct from a missing object."""
    s3 = FakeS3Client()
    service = S3WritingImageDeliveryService(s3, "goa-writing-files")

    with pytest.raises(ValueError):
        service.generate_image_url("", uuid4())

    # Never touched S3 for a key we could reject outright.
    assert s3.head_calls == []
    assert s3.calls == []
