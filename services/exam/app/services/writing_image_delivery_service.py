import logging
from typing import Any
from uuid import UUID

logger = logging.getLogger(__name__)


class WritingImageUnavailableError(RuntimeError):
    """The stimulus image for an Academic Writing Task 1 question is not in the bucket.

    Distinct from ValueError, which means the key itself is malformed. This one
    means the key is well-formed and the object simply is not there -- the exact
    BUG-022 shape, but for a writing chart instead of a listening section.
    """


class S3WritingImageDeliveryService:
    """Mints a browser-reachable pre-signed URL for a Writing Task 1 stimulus image.

    Two failure modes this guards against, both learned from the listening path:

      * BUG-022: pre-signing never touches S3, so an empty bucket yields a
        perfectly-formed URL, a 200 and a running exam clock -- then a 404 the
        moment the browser loads the image. We HEAD the object first and refuse
        before any session state exists if it is missing.

      * BUG-016: a pre-signed URL is signed for a specific host (SigV4 signs the
        Host header). Signing against the internal ``localstack:4566`` endpoint
        produces a URL no browser can resolve. The caller therefore builds this
        service's ``s3_client`` against the *public* endpoint so the signature is
        valid for the host the browser will actually request.
    """

    PRESIGNED_URL_EXPIRY_SECONDS = 7200

    def __init__(
        self,
        s3_client: Any,
        bucket: str,
        head_client: Any | None = None,
    ) -> None:
        self.s3_client = s3_client
        self.bucket = bucket
        # The existence check and the signature are two different concerns with
        # two different audiences. The presign (``s3_client``) is signed for the
        # PUBLIC host the browser will request (BUG-016). The HEAD only has to
        # reach S3 from the server side. In a split-horizon dev setup those are
        # different endpoints -- LocalStack is ``localstack:4566`` on the docker
        # network but published at ``localhost:4566`` for the browser, and a
        # container cannot resolve its own ``localhost`` to the published port,
        # so a single client signed for the public host cannot also HEAD from
        # inside the container. ``head_client`` lets the caller point the check
        # at the internal endpoint. It defaults to ``s3_client`` so production
        # (where the two endpoints coincide) and the unit tests (one fake) are
        # unchanged.
        self.head_client = head_client or s3_client

    def generate_image_url(
        self,
        image_s3_key: str,
        session_id: UUID,
    ) -> str:
        if not image_s3_key:
            raise ValueError("Writing question has no image S3 key")

        # Verify the object exists before handing out a URL for it. See BUG-022
        # note above: this one HEAD turns a silent 404-on-load into a named
        # refusal before the candidate ever starts the task.
        if not self._object_exists(image_s3_key):
            logger.error(
                "writing_image_missing",
                extra={
                    "bucket": self.bucket,
                    "missing_key": image_s3_key,
                },
            )
            raise WritingImageUnavailableError(
                f"Writing stimulus image is missing from "
                f"s3://{self.bucket}: {image_s3_key}"
            )

        return self.s3_client.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": self.bucket,
                "Key": image_s3_key,
                # inline so the browser renders the chart rather than downloading
                # it; the session id keeps each candidate's signature distinct
                # even when the same test is reused across the bank.
                "ResponseContentDisposition": (
                    f'inline; filename="task1-stimulus"; session="{session_id}"'
                ),
            },
            ExpiresIn=self.PRESIGNED_URL_EXPIRY_SECONDS,
        )

    def _object_exists(self, key: str) -> bool:
        try:
            self.head_client.head_object(Bucket=self.bucket, Key=key)
        except Exception:
            # botocore raises ClientError for 404/403 alike, and a stubbed client
            # in tests may raise something else entirely. Either way the object
            # is not usable, and treating that as "present" is the failure this
            # guard exists to prevent.
            return False
        return True
