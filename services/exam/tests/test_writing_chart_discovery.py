"""Chart crop discovery for Academic Writing Task 1 (Stage 2 parse).

The bug these cover: the crops on disk are named after the book_ref
(``ielts-15-test-1-task1.png``) and live in ``assets/charts``, while
``parse_books.py`` looked only for the slug spelling (``IELTS15-test1-task1.png``)
in ``data/charts``. ``Path.exists()`` returned False, ``_upload_writing_chart``
returned None, and the parsed JSON simply carried no image key — indistinguishable
from the legitimate General Training case, so nothing warned. The chart never
reached S3 and Writing could not serve the task.
"""

import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import parse_books  # noqa: E402


class FakeS3Client:
    """Records uploads so the key and Content-Type can be asserted."""

    def __init__(self) -> None:
        self.uploads: list[dict[str, Any]] = []

    def upload_file(
        self,
        filename: str,
        bucket: str,
        key: str,
        ExtraArgs: dict[str, Any] | None = None,  # noqa: N803 - boto3 spelling
    ) -> None:
        self.uploads.append(
            {
                "filename": filename,
                "bucket": bucket,
                "key": key,
                "extra_args": ExtraArgs or {},
            }
        )


@pytest.fixture
def chart_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Point the module at an empty (primary, fallback) pair under tmp_path."""
    primary = tmp_path / "assets" / "charts"
    fallback = tmp_path / "data" / "charts"
    primary.mkdir(parents=True)
    fallback.mkdir(parents=True)
    monkeypatch.setattr(parse_books, "CHART_SEARCH_DIRS", (primary, fallback))
    return primary, fallback


@pytest.fixture
def s3(monkeypatch: pytest.MonkeyPatch) -> FakeS3Client:
    client = FakeS3Client()
    monkeypatch.setattr(parse_books, "_get_s3_client", lambda: client)
    return client


def test_book_ref_named_crop_in_assets_is_found(chart_dirs) -> None:
    """The real-world filename that used to be missed entirely."""
    primary, _ = chart_dirs
    (primary / "ielts-15-test-1-task1.png").write_bytes(b"png")

    resolved = parse_books._resolve_chart_path("IELTS15", 1, "IELTS-15")

    assert resolved == primary / "ielts-15-test-1-task1.png"


def test_legacy_slug_named_crop_in_fallback_dir_still_works(chart_dirs) -> None:
    """The previously documented location and spelling must not regress."""
    _, fallback = chart_dirs
    (fallback / "IELTS15-test1-task1.png").write_bytes(b"png")

    resolved = parse_books._resolve_chart_path("IELTS15", 1, "IELTS-15")

    assert resolved == fallback / "IELTS15-test1-task1.png"


def test_match_is_case_insensitive(chart_dirs) -> None:
    """book_ref is IELTS-15 but crops are saved lowercase; Linux is case-sensitive."""
    primary, _ = chart_dirs
    (primary / "IELTS-15-TEST-1-TASK1.PNG").write_bytes(b"png")

    assert parse_books._resolve_chart_path("IELTS15", 1, "IELTS-15") is not None


def test_primary_dir_wins_when_both_have_a_crop(chart_dirs) -> None:
    primary, fallback = chart_dirs
    (primary / "ielts-15-test-1-task1.png").write_bytes(b"primary")
    (fallback / "IELTS15-test1-task1.png").write_bytes(b"fallback")

    resolved = parse_books._resolve_chart_path("IELTS15", 1, "IELTS-15")

    assert resolved.read_bytes() == b"primary"


def test_absent_crop_returns_none_and_uploads_nothing(chart_dirs, s3) -> None:
    """General Training Task 1 is a letter: no crop is the correct outcome."""
    assert parse_books._resolve_chart_path("IELTS15", 4, "IELTS-15") is None
    assert parse_books._upload_writing_chart("IELTS15", 4, "IELTS-15") is None
    assert s3.uploads == []


def test_png_key_is_unchanged_from_the_shipped_convention(chart_dirs, s3) -> None:
    """Existing rows and pre-signed URLs depend on this exact key."""
    primary, _ = chart_dirs
    (primary / "ielts-15-test-1-task1.png").write_bytes(b"png")

    key = parse_books._upload_writing_chart("IELTS15", 1, "IELTS-15")

    assert key == "charts/IELTS-15-test-1-task1.png"
    assert s3.uploads[0]["key"] == "charts/IELTS-15-test-1-task1.png"
    assert s3.uploads[0]["extra_args"]["ContentType"] == "image/png"


def test_jpeg_crop_keeps_its_extension_and_content_type(chart_dirs, s3) -> None:
    """A .jpg crop used to be skipped in silence; serving it as PNG would be worse."""
    primary, _ = chart_dirs
    (primary / "ielts-15-test-2-task1.jpg").write_bytes(b"jpg")

    key = parse_books._upload_writing_chart("IELTS15", 2, "IELTS-15")

    assert key == "charts/IELTS-15-test-2-task1.jpg"
    assert s3.uploads[0]["extra_args"]["ContentType"] == "image/jpeg"


def test_upload_failure_is_not_fatal(chart_dirs, monkeypatch) -> None:
    """A transient S3 error must not discard a successfully parsed test."""
    primary, _ = chart_dirs
    (primary / "ielts-15-test-1-task1.png").write_bytes(b"png")

    class BrokenS3:
        def upload_file(self, *args: Any, **kwargs: Any) -> None:
            raise RuntimeError("connection reset")

    monkeypatch.setattr(parse_books, "_get_s3_client", lambda: BrokenS3())

    assert parse_books._upload_writing_chart("IELTS15", 1, "IELTS-15") is None
