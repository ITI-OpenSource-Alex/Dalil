import logging
import re
from typing import Any
from uuid import UUID

logger = logging.getLogger(__name__)


class ListeningAudioUnavailableError(RuntimeError):
    """The section audio for a listening test is not in the bucket.

    Distinct from ValueError, which means the key itself is malformed. This one
    means the key is well-formed and the object simply is not there.
    """


class S3AudioDeliveryService:
    PRESIGNED_URL_EXPIRY_SECONDS = 7200
    SECTION_COUNT = 4

    def __init__(
        self, s3_client: Any, bucket: str, head_client: Any | None = None
    ) -> None:
        self.s3_client = s3_client
        self.head_client = head_client or s3_client
        self.bucket = bucket

    def generate_section_urls(
        self,
        audio_s3_key: str,
        session_id: UUID,
    ) -> list[str]:
        keys = [
            self._section_key(audio_s3_key, section)
            for section in range(1, self.SECTION_COUNT + 1)
        ]

        # Verify the objects exist before handing out URLs for them.
        #
        # Pre-signing does not touch S3, so an empty bucket produced four
        # perfectly-formed URLs, a 200, a session row and a 40-minute clock --
        # and four 404s the moment the candidate pressed play (BUG-022). Failing
        # here costs one HEAD per section and turns a silent, unattributable
        # dead end into a named error before any exam state is created.
        missing = [key for key in keys if not self._object_exists(key)]
        if missing:
            logger.error(
                "listening_audio_missing",
                extra={
                    "bucket": self.bucket,
                    "missing_keys": missing,
                    "missing_count": len(missing),
                    "expected_sections": self.SECTION_COUNT,
                },
            )
            raise ListeningAudioUnavailableError(
                f"{len(missing)} of {self.SECTION_COUNT} listening audio sections "
                f"are missing from s3://{self.bucket}: {', '.join(missing)}"
            )

        return [
            self.s3_client.generate_presigned_url(
                "get_object",
                Params={
                    "Bucket": self.bucket,
                    "Key": key,
                    # This makes the signature fresh for each exam session even
                    # when a user eventually exhausts the unseen question bank.
                    "ResponseContentDisposition": (
                        f'inline; filename="section{section}.mp3"; '
                        f'session="{session_id}"'
                    ),
                },
                ExpiresIn=self.PRESIGNED_URL_EXPIRY_SECONDS,
            )
            for section, key in enumerate(keys, start=1)
        ]

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

    def _section_key(self, audio_s3_key: str, section: int) -> str:
        if not audio_s3_key:
            raise ValueError("Listening test has no audio S3 key")

        filename_pattern = re.compile(r"section\d+\.mp3$", re.IGNORECASE)
        if not filename_pattern.search(audio_s3_key):
            raise ValueError("Listening audio S3 key must end with section<number>.mp3")
        return filename_pattern.sub(f"section{section}.mp3", audio_s3_key)
