"""
app/ingestion/writing_parser.py
-------------------------------
Cambridge IELTS Writing prompt parser.

Extracts Task 1 (letter/report/graph description) and Task 2 (essay) prompts
from Cambridge IELTS PDF or text content. Each test produces one record with
skill_area='writing', questions JSONB containing task 1 + task 2, and
time_limit_seconds=3600.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any

from app.ingestion.parser import BaseParser

logger = logging.getLogger("exam_service.ingestion.writing_parser")

# Project root — three levels up from app/ingestion/writing_parser.py, matching
# pipeline_config.BASE_DIR. Charts a human has extracted from the source PDFs are
# expected under <root>/assets/charts/ using the standard filename below.
_BASE_DIR = Path(__file__).resolve().parent.parent.parent
_CHARTS_DIR = Path(os.getenv("EXAM_CHARTS_DIR", str(_BASE_DIR / "assets" / "charts")))
# The Writing service fetches the stimulus from ITS OWN S3_BUCKET (writing
# config.py -> agents._fetch_chart_bytes), which is goa-writing-files. We MUST
# upload the chart to that exact bucket or the reader 404s with "Stimulus image
# not found". This parser runs inside the EXAM container, whose S3_BUCKET is
# goa-exam-audio (a different bucket for listening audio) -- so we must NOT fall
# back to the ambient S3_BUCKET, or the chart lands in the wrong place. Target
# goa-writing-files by default; WRITING_IMAGE_BUCKET overrides only if the
# Writing service is ever reconfigured to read elsewhere.
_IMAGE_BUCKET = os.getenv("WRITING_IMAGE_BUCKET", "goa-writing-files")
# Match however the rest of the stack reaches LocalStack: user/exam services use
# AWS_ENDPOINT, writing/ingestion use AWS_ENDPOINT_URL. Accept either.
_S3_ENDPOINT_URL = (
    os.getenv("AWS_ENDPOINT_URL")
    or os.getenv("AWS_ENDPOINT")
    or os.getenv("S3_ENDPOINT_URL")
)
_S3_REGION = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION", "us-east-1")


class WritingParser(BaseParser):
    """Extracts IELTS Writing Task 1 and Task 2 prompts."""

    def parse_text(self, content: str | Any) -> dict[str, Any]:
        text = str(content)
        metadata = self._infer_metadata(text)
        metadata["skill_area"] = "writing"

        task1_prompt = self._extract_task(text, task_number=1)
        task2_prompt = self._extract_task(text, task_number=2)

        exam_type = metadata.get("exam_type", "academic")
        book_ref = metadata.get("book_ref", "IELTS-unknown")
        test_number = metadata.get("test_number", 1)

        questions: list[dict[str, Any]] = []
        if task1_prompt:
            # Academic Task 1 cannot be graded without its chart/graph/diagram, so
            # the Writing service refuses (502) when image_s3_key is null. We set a
            # key ONLY when a real chart file is present on disk and uploads
            # cleanly — never a fabricated key pointing at a missing S3 object,
            # which would only move the failure downstream ("Stimulus image not
            # found"). General Training Task 1 is a letter and needs no image.
            image_s3_key = None
            if exam_type == "academic":
                image_s3_key = self.resolve_task1_image(book_ref, test_number)

            questions.append(
                {
                    "task_key": "task1",
                    "number": 1,
                    "prompt": task1_prompt,
                    "question_type": "Writing Task 1",
                    "instructions": self._detect_task1_type(task1_prompt),
                    "passage_number": None,
                    "section_number": None,
                    "image_s3_key": image_s3_key,
                }
            )
        if task2_prompt:
            questions.append(
                {
                    "task_key": "task2",
                    "number": 2,
                    "prompt": task2_prompt,
                    "question_type": "Writing Task 2",
                    "instructions": "Write an essay of at least 250 words.",
                    "passage_number": None,
                    "section_number": None,
                }
            )

        return {
            "book_ref": book_ref,
            "test_number": test_number,
            "exam_type": exam_type,
            "skill_area": "writing",
            "passage_text": None,
            "questions": questions,
            "answer_key": {},
            "time_limit_seconds": 3600,
        }

    def _image_filename(self, book_ref: str, test_number: int) -> str:
        """Standard chart filename, e.g. IELTS-15 test 1 -> ielts-15-test-1-task1.png.

        Falls back to the raw (slugified) book_ref when no IELTS number is present
        so an operator can still drop a file for an ``IELTS-unknown`` record.
        """
        m = re.search(r"(\d{1,2})", book_ref)
        book_slug = f"ielts-{m.group(1)}" if m else book_ref.lower().replace(" ", "-")
        return f"{book_slug}-test-{test_number}-task1.png"

    def resolve_task1_image(self, book_ref: str, test_number: int) -> str | None:
        """Return an S3 key for the Task 1 chart, or None if unavailable.

        A key is returned only when the local chart file exists AND is confirmed
        present in S3 (uploaded here, or already there). Any missing file, missing
        boto3, or upload error yields None so the stored data never claims an image
        that cannot be fetched.

        Public because the ingestion pipeline (parse_books.py) overrides book_ref
        and test_number with authoritative slug-derived values AFTER parse_text
        returns, and must re-resolve the key against those — mirroring how it sets
        the listening audio_s3_key. A mid-book test block rarely contains the book
        title, so the value inferred inside parse_text can be wrong.
        """
        local_path = _CHARTS_DIR / self._image_filename(book_ref, test_number)
        if not local_path.is_file():
            logger.info(
                "task1 chart not found on disk; leaving image_s3_key=None "
                "(book_ref=%s test=%s path=%s)",
                book_ref,
                test_number,
                local_path,
            )
            return None

        s3_key = f"charts/{self._image_filename(book_ref, test_number)}"
        if self._upload_chart(local_path, s3_key):
            logger.info("task1 chart uploaded s3://%s/%s", _IMAGE_BUCKET, s3_key)
            return s3_key
        logger.warning(
            "task1 chart present at %s but upload to s3://%s/%s failed; "
            "leaving image_s3_key=None",
            local_path,
            _IMAGE_BUCKET,
            s3_key,
        )
        return None

    def _upload_chart(self, local_path: Path, s3_key: str) -> bool:
        """Upload the chart to S3, returning True only on confirmed presence.

        boto3 is imported lazily so ordinary text parsing never requires it — the
        import only happens when a real chart file exists to upload.
        """
        try:
            import boto3  # noqa: PLC0415 — intentional lazy import
            from botocore.exceptions import BotoCoreError, ClientError
        except ImportError:
            logger.warning("boto3 unavailable; cannot upload %s", s3_key)
            return False

        try:
            client = boto3.client(
                "s3",
                region_name=_S3_REGION,
                endpoint_url=_S3_ENDPOINT_URL,
            )
            client.upload_file(
                str(local_path),
                _IMAGE_BUCKET,
                s3_key,
                ExtraArgs={"ContentType": "image/png"},
            )
            # Confirm the object is actually retrievable before trusting the key.
            client.head_object(Bucket=_IMAGE_BUCKET, Key=s3_key)
            return True
        except (BotoCoreError, ClientError, OSError) as exc:
            logger.warning("chart upload failed for %s: %s", s3_key, exc)
            return False

    def _extract_task(self, text: str, *, task_number: int) -> str | None:
        patterns = [
            re.compile(
                rf"(?i)WRITING\s+TASK\s+{task_number}\b(.*?)(?=WRITING\s+TASK\s+|$)",
                re.DOTALL,
            ),
            re.compile(
                rf"(?i)TASK\s+{task_number}\b(.*?)(?=TASK\s+\d|$)",
                re.DOTALL,
            ),
        ]

        for pattern in patterns:
            m = pattern.search(text)
            if m:
                block = m.group(1).strip()
                prompt = self._clean_prompt(block)
                if prompt and len(prompt) > 20:
                    return prompt

        return None

    def _clean_prompt(self, text: str) -> str:
        text = self._strip_section_bleed(text)
        lines = []
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if re.match(r"(?i)^(you should spend|write at least)", stripped):
                lines.append(stripped)
                continue
            if re.match(r"(?i)^(page \d|copyright)", stripped):
                continue
            if self._is_ocr_noise(stripped):
                continue
            lines.append(stripped)
        return "\n".join(lines)

    # Headers that mark the start of a different exam section. The writing-task
    # regex stops only at the next "TASK n", so anything the OCR appended after
    # Task 2 — most often the SPEAKING section — is captured verbatim. Cutting the
    # block at the first of these headers keeps a task prompt to just its own text.
    _SECTION_BOUNDARY = re.compile(
        r"(?im)^\s*(speaking|listening|reading|part\s+\d+|section\s+\d+"
        r"|discussion\s+topics|example\s+questions)\b.*$"
    )

    def _strip_section_bleed(self, text: str) -> str:
        match = self._SECTION_BOUNDARY.search(text)
        if match:
            return text[: match.start()].rstrip()
        return text

    def _is_ocr_noise(self, line: str) -> bool:
        """Drop short lines that carry no letters or are stray OCR artefacts.

        Targets fragments like "2@ 128] 29", "e", "Ld", "I" that the scanner emits
        between real sentences — not real prompt content, which is always a proper
        clause. Kept deliberately conservative: only very short lines, and only
        when they lack a run of alphabetic characters forming a word.
        """
        if len(line) > 40:
            return False
        letters = re.sub(r"[^A-Za-z]", "", line)
        # No real word at all (pure symbols/digits), or a 1-2 char orphan token.
        if not re.search(r"[A-Za-z]{3,}", line):
            return True
        if len(letters) <= 2 and len(line.split()) <= 1:
            return True
        return False

    def _detect_task1_type(self, prompt: str) -> str:
        lowered = prompt.lower()
        if "letter" in lowered:
            return "Write a letter of at least 150 words."
        if "graph" in lowered or "chart" in lowered or "diagram" in lowered:
            return "Summarise the information by selecting and reporting the main features."
        if "map" in lowered or "plan" in lowered:
            return "Summarise the information by selecting and reporting the main features."
        if "process" in lowered or "flow" in lowered:
            return "Summarise the information by selecting and reporting the main features."
        return "Write at least 150 words."
