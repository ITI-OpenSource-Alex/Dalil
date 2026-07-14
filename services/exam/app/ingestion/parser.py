from __future__ import annotations

import hashlib
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("exam_service.ingestion.parser")

# Default directory for cached OCR page text.  Override via the
# ``OCR_CACHE_DIR`` environment variable.
_DEFAULT_CACHE_DIR = Path(__file__).resolve().parent.parent.parent / ".cache" / "ocr"


@dataclass(slots=True)
class ParsedQuestion:
    prompt: str
    question_type: str
    answer: str | None = None
    number: int | None = None
    instructions: str | None = None
    passage_number: int | None = None
    section_number: int | None = None


@dataclass(slots=True)
class ParsedTest:
    book_ref: str
    test_number: int
    exam_type: str
    skill_area: str
    passage_text: str | None = None
    questions: list[ParsedQuestion] = field(default_factory=list)
    answer_key: dict[str, Any] = field(default_factory=dict)
    section_type: str | None = None
    audio_s3_key: str | None = None
    time_limit_seconds: int | None = None


class BaseParser:
    SUPPORTED_QUESTION_TYPES = {
        "Multiple Choice": "Multiple Choice",
        "Matching Headings": "Matching Headings",
        "Matching Information": "Matching Information",
        "Matching Features": "Matching Features",
        "Matching Sentence Endings": "Matching Sentence Endings",
        "True / False / Not Given": "True / False / Not Given",
        "Yes / No / Not Given": "Yes / No / Not Given",
        "Sentence Completion": "Sentence Completion",
        "Summary Completion": "Summary Completion",
        "Notes Completion": "Notes Completion",
        "Table Completion": "Table Completion",
        "Flow Chart Completion": "Flow Chart Completion",
        "Diagram Labelling": "Diagram Labelling",
        "Short Answer": "Short Answer",
    }

    def parse(self, content: str | Path) -> dict[str, Any]:
        return self.parse_text(content)

    def parse_text(self, content: str | Path) -> dict[str, Any]:
        raise NotImplementedError

    def parse_pdf(
        self,
        path: str | Path,
        *,
        first_page: int | None = None,
        last_page: int | None = None,
    ) -> dict[str, Any]:
        """Extract text from a PDF and parse it.

        Parameters
        ----------
        first_page, last_page : int | None
            1-based inclusive page range.  When provided, only the specified
            pages are processed — both for pdfplumber and OCR fallback.
        """
        source_path = Path(path)
        text, page_count = self._extract_pdf_text(
            source_path, first_page=first_page, last_page=last_page
        )
        logger.info(
            "Using pdfplumber extraction",
            extra={"source": str(source_path), "pages_processed": page_count},
        )

        if len(text.strip()) < 100:
            logger.info(
                "Searchable text is too short or empty. Falling back to OCR.",
                extra={"source": str(source_path), "pages_processed": page_count},
            )
            text, ocr_page_count = self._extract_pdf_text_with_ocr(
                source_path, first_page=first_page, last_page=last_page
            )
            logger.info(
                "Using OCR fallback",
                extra={"source": str(source_path), "pages_processed": ocr_page_count},
            )

        if not text.strip():
            raise RuntimeError(f"No text extracted from PDF: {source_path}")

        try:
            name = source_path.name
        except Exception:
            name = str(path)
        content = f"{name}\n{text}"
        return self.parse_text(content)

    def _extract_pdf_text(
        self,
        path: str | Path,
        *,
        first_page: int | None = None,
        last_page: int | None = None,
    ) -> tuple[str, int]:
        try:
            import pdfplumber  # type: ignore
        except ImportError as exc:  # pragma: no cover - dependency guard
            raise RuntimeError("pdfplumber is required to parse PDF content") from exc

        with pdfplumber.open(str(path)) as pdf:
            total = len(pdf.pages)
            start = max((first_page or 1) - 1, 0)
            end = min(last_page or total, total)
            pages = []
            for page in pdf.pages[start:end]:
                extracted = page.extract_text(layout=True) or page.extract_text() or ""
                pages.append(extracted)
        return self._normalize_text("\n".join(pages)), end - start

    def _extract_pdf_text_with_ocr(
        self,
        path: str | Path,
        *,
        first_page: int | None = None,
        last_page: int | None = None,
    ) -> tuple[str, int]:
        try:
            import pytesseract  # type: ignore
        except ImportError as exc:  # pragma: no cover - dependency guard
            raise RuntimeError(
                "OCR fallback requires 'pytesseract'. Install it with pip install pytesseract."
            ) from exc

        try:
            from pdf2image import convert_from_path, pdfinfo_from_path  # type: ignore
        except ImportError as exc:  # pragma: no cover - dependency guard
            raise RuntimeError(
                "OCR fallback requires 'pdf2image'. Install it with pip install pdf2image."
            ) from exc

        try:
            from PIL import ImageOps  # type: ignore
        except ImportError as exc:  # pragma: no cover - dependency guard
            raise RuntimeError(
                "OCR fallback requires 'Pillow'. Install it with pip install Pillow."
            ) from exc

        try:
            info = pdfinfo_from_path(str(path))
            total_pages = int(info.get("Pages", 0))
        except Exception as exc:
            raise RuntimeError(f"OCR fallback could not inspect PDF pages: {path}") from exc

        if total_pages <= 0:
            raise RuntimeError(f"OCR fallback could not render pages from PDF: {path}")

        start = max((first_page or 1), 1)
        end = min((last_page or total_pages), total_pages)
        page_range = range(start, end + 1)
        pages_to_process = len(page_range)

        # Resolve cache directory and compute PDF hash for cache keys
        cache_dir = self._resolve_cache_dir(path)
        pdf_hash = self._compute_pdf_hash(path)

        from concurrent.futures import ThreadPoolExecutor
        import pytesseract
        from PIL import ImageOps
        from pdf2image import convert_from_path

        max_workers = min(os.cpu_count() or 2, 4)

        def process_page(idx: int) -> str:
            # Check cache first
            cached = self._read_page_cache(cache_dir, pdf_hash, idx)
            if cached is not None:
                logger.debug("Cache hit for page %d", idx)
                return cached

            try:
                rendered = convert_from_path(str(path), dpi=150, first_page=idx, last_page=idx)
                if not rendered:
                    return ""
                image = rendered[0]
                grayscale = ImageOps.grayscale(image)
                thresholded = grayscale.point(lambda x: 0 if x < 160 else 255, mode="1")
                text = pytesseract.image_to_string(thresholded) or ""
                image.close()
                grayscale.close()
                thresholded.close()

                # Write to cache
                self._write_page_cache(cache_dir, pdf_hash, idx, text)

                logger.info("OCR page %d/%d complete", idx, end)
                return text
            except Exception as e:
                logger.warning("Error on page %d: %s", idx, e)
                return ""

        pages: list[str] = []
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            pages = list(executor.map(process_page, page_range))

        merged_text = self._normalize_text("\n".join(pages))
        if not merged_text.strip():
            raise RuntimeError(f"OCR fallback returned no text for PDF: {path}")

        logger.info(
            "OCR complete: %d pages processed (%d from cache)",
            pages_to_process,
            sum(1 for idx in page_range if self._read_page_cache(cache_dir, pdf_hash, idx) is not None),
        )
        return merged_text, pages_to_process

    # ------------------------------------------------------------------
    # OCR Caching
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_cache_dir(path: str | Path) -> Path:
        env_dir = os.environ.get("OCR_CACHE_DIR")
        if env_dir:
            return Path(env_dir)
        return _DEFAULT_CACHE_DIR

    @staticmethod
    def _compute_pdf_hash(path: str | Path) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            while chunk := f.read(1 << 20):  # 1 MiB chunks
                h.update(chunk)
        return h.hexdigest()[:16]

    @staticmethod
    def _read_page_cache(cache_dir: Path, pdf_hash: str, page: int) -> str | None:
        cache_file = cache_dir / pdf_hash / f"page_{page:04d}.txt"
        if cache_file.exists():
            return cache_file.read_text(encoding="utf-8")
        return None

    @staticmethod
    def _write_page_cache(cache_dir: Path, pdf_hash: str, page: int, text: str) -> None:
        page_dir = cache_dir / pdf_hash
        page_dir.mkdir(parents=True, exist_ok=True)
        cache_file = page_dir / f"page_{page:04d}.txt"
        cache_file.write_text(text, encoding="utf-8")

    def _normalize_text(self, text: str) -> str:
        cleaned_lines: list[str] = []
        seen: set[str] = set()
        for raw_line in text.splitlines():
            line = re.sub(r"\s+", " ", raw_line).strip()
            if not line:
                continue
            if re.fullmatch(r"\d+", line):
                continue
            if "copyright" in line.lower() or "cambridge university press" in line.lower():
                continue
            if line.lower().startswith("page "):
                continue
            if line not in seen:
                cleaned_lines.append(line)
                seen.add(line)
        return "\n".join(cleaned_lines)

    def _infer_metadata(self, content: str, source: str | None = None) -> dict[str, Any]:
        metadata: dict[str, Any] = {
            "book_ref": "IELTS-unknown",
            "test_number": 1,
            "exam_type": "academic",
            "skill_area": "reading",
        }
        text = content.lower()
        source_text = (source or "").lower()

        if re.search(r"ielts\s*(\d{1,2})", content, re.IGNORECASE):
            book_number = re.search(r"ielts\s*(\d{1,2})", content, re.IGNORECASE).group(1)
            metadata["book_ref"] = f"IELTS-{book_number}"
        elif re.search(r"ielts\s*(\d{1,2})", source_text, re.IGNORECASE):
            book_number = re.search(r"ielts\s*(\d{1,2})", source_text, re.IGNORECASE).group(1)
            metadata["book_ref"] = f"IELTS-{book_number}"

        test_match = re.search(r"test\s*(\d+)", content, re.IGNORECASE)
        if test_match:
            metadata["test_number"] = int(test_match.group(1))
        elif re.search(r"test\s*(\d+)", source_text, re.IGNORECASE):
            metadata["test_number"] = int(re.search(r"test\s*(\d+)", source_text, re.IGNORECASE).group(1))

        if "academic" in text:
            metadata["exam_type"] = "academic"
        elif "general" in text:
            metadata["exam_type"] = "general"
        if "academic" in source_text:
            metadata["exam_type"] = "academic"
        elif "general" in source_text:
            metadata["exam_type"] = "general"

        return metadata

    def _parse_answer_key(self, value: str) -> dict[str, Any]:
        answers: dict[str, Any] = {}
        for match in re.finditer(r"(\d+)\.\s*([^\d|]+)", value.strip()):
            answers[match.group(1)] = match.group(2).strip()
        return answers

    def _extract_answer_key(self, content: str) -> dict[str, Any]:
        lines = [line.strip() for line in content.splitlines() if line.strip()]
        answers: dict[str, Any] = {}
        in_key_section = False
        for line in lines:
            lowered = line.lower()
            if lowered.startswith("answer key") or lowered.startswith("answer keys") or lowered.startswith("answers"):
                in_key_section = True
                continue
            if in_key_section and re.match(r"^(reading|listening|section|passage)\b", lowered):
                break
            if in_key_section:
                match = re.match(r"^(\d{1,2})\s*[\.)]\s*(.+)$", line)
                if match:
                    answers[match.group(1)] = match.group(2).strip()
                    continue
                match = re.match(r"^(\d{1,2})\s+([A-Za-z0-9/\-() .]+)$", line)
                if match:
                    answers[match.group(1)] = match.group(2).strip()
        return answers

    def _classify_question_type(self, prompt: str) -> str:
        lowered = prompt.lower()
        if "short answer" in lowered or "no more than two words" in lowered:
            return "Short Answer"
        if "matching headings" in lowered or "choose the correct heading" in lowered:
            return "Matching Headings"
        if "matching information" in lowered or "information" in lowered and "match" in lowered:
            return "Matching Information"
        if "matching features" in lowered or "features" in lowered and "match" in lowered:
            return "Matching Features"
        if "matching sentence endings" in lowered or "sentence endings" in lowered:
            return "Matching Sentence Endings"
        if "true / false / not given" in lowered or "true false not given" in lowered or "true / false" in lowered:
            return "True / False / Not Given"
        if "yes / no / not given" in lowered or "yes no not given" in lowered:
            return "Yes / No / Not Given"
        if "complete the sentence" in lowered or "sentence completion" in lowered:
            return "Sentence Completion"
        if "complete the summary" in lowered or "summary completion" in lowered:
            return "Summary Completion"
        if "complete the notes" in lowered or "notes completion" in lowered:
            return "Notes Completion"
        if "complete the table" in lowered or "table completion" in lowered:
            return "Table Completion"
        if "flow chart" in lowered or "flow-chart" in lowered:
            return "Flow Chart Completion"
        if "label the diagram" in lowered or "diagram" in lowered and "label" in lowered:
            return "Diagram Labelling"
        if "choose the correct letter" in lowered or "which of the following" in lowered or "choose the correct option" in lowered:
            return "Multiple Choice"
        if "choose the correct heading" in lowered:
            return "Matching Headings"
        if "complete" in lowered or "fill" in lowered or "one word" in lowered:
            return "Sentence Completion"
        return "Multiple Choice"

    def _question_payload(self, question: ParsedQuestion) -> dict[str, Any]:
        return {
            "number": question.number,
            "prompt": question.prompt,
            "question_type": question.question_type,
            "instructions": question.instructions,
            "passage_number": question.passage_number,
            "section_number": question.section_number,
        }
