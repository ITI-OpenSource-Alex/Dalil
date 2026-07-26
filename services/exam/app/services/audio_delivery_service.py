import re
from typing import Any
from uuid import UUID


class S3AudioDeliveryService:
    PRESIGNED_URL_EXPIRY_SECONDS = 7200
    SECTION_COUNT = 4

    def __init__(self, s3_client: Any, bucket: str) -> None:
        self.s3_client = s3_client
        self.bucket = bucket

    def generate_section_urls(
        self,
        audio_s3_key: str,
        session_id: UUID,
    ) -> list[str]:
        return [
            self.s3_client.generate_presigned_url(
                "get_object",
                Params={
                    "Bucket": self.bucket,
                    "Key": self._section_key(audio_s3_key, section),
                    # This makes the signature fresh for each exam session even
                    # when a user eventually exhausts the unseen question bank.
                    "ResponseContentDisposition": (
                        f'inline; filename="section{section}.mp3"; '
                        f'session="{session_id}"'
                    ),
                },
                ExpiresIn=self.PRESIGNED_URL_EXPIRY_SECONDS,
            )
            for section in range(1, self.SECTION_COUNT + 1)
        ]

    def _section_key(self, audio_s3_key: str, section: int) -> str:
        if not audio_s3_key:
            raise ValueError("Listening test has no audio S3 key")

        filename_pattern = re.compile(r"section\d+\.mp3$", re.IGNORECASE)
        if not filename_pattern.search(audio_s3_key):
            raise ValueError("Listening audio S3 key must end with section<number>.mp3")
        return filename_pattern.sub(f"section{section}.mp3", audio_s3_key)
