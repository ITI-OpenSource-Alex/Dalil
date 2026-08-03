from __future__ import annotations

import hashlib
import logging
import os
import platform
import re
import shutil
from pathlib import Path

logger = logging.getLogger("exam_service.ingestion.ocr")

_DEFAULT_CACHE_DIR = Path(__file__).resolve().parent.parent.parent / ".cache" / "ocr"

_WINDOWS_POPPLER_SEARCH_DIRS = [
    Path(os.environ.get("LOCALAPPDATA", "")) / "poppler" / "Library" / "bin",
    Path(os.environ.get("PROGRAMFILES", "")) / "poppler" / "bin",
    Path(os.environ.get("PROGRAMFILES", "")) / "poppler" / "Library" / "bin",
    Path("C:/") / "tools" / "poppler" / "bin",
    Path("C:/") / "poppler" / "bin",
]


def _resolve_poppler_path() -> str | None:
    env = os.environ.get("POPPLER_PATH")
    if env:
        p = Path(env)
        if p.is_dir():
            return str(p)
        logger.warning("POPPLER_PATH=%s is not a valid directory", env)

    if shutil.which("pdftoppm"):
        return None

    if platform.system() == "Windows":
        for candidate in _WINDOWS_POPPLER_SEARCH_DIRS:
            if candidate.is_dir() and any(candidate.glob("pdftoppm*")):
                logger.info("Auto-detected poppler at %s", candidate)
                return str(candidate)

    return None


def _check_poppler_available(poppler_path: str | None) -> None:
    if poppler_path:
        pdftoppm = Path(poppler_path) / (
            "pdftoppm.exe" if platform.system() == "Windows" else "pdftoppm"
        )
        if not pdftoppm.exists():
            raise RuntimeError(
                f"Poppler binary 'pdftoppm' not found at {poppler_path}.\n"
                "Install poppler:\n"
                "  Windows: download from https://github.com/oschwartz10612/poppler-windows/releases\n"
                "           and set POPPLER_PATH=C:\\path\\to\\poppler\\bin\n"
                "  Linux:   apt-get install poppler-utils  OR  apk add poppler-utils\n"
                "  macOS:   brew install poppler"
            )
        return

    if not shutil.which("pdftoppm"):
        raise RuntimeError(
            "Poppler is not installed or not in PATH.\n"
            "pdf2image requires the 'pdftoppm' and 'pdfinfo' binaries from poppler.\n"
            "Install poppler:\n"
            "  Windows: download from https://github.com/oschwartz10612/poppler-windows/releases\n"
            "           and set POPPLER_PATH=C:\\path\\to\\poppler\\bin\n"
            "  Linux:   apt-get install poppler-utils  OR  apk add poppler-utils\n"
            "  macOS:   brew install poppler"
        )


class OcrService:
    """PDF text extraction with pdfplumber and OCR fallback.

    Shared by BaseParser.parse_pdf() and the stage-based pipeline scripts.
    No parsing logic, no database code.
    """

    def __init__(self) -> None:
        self._poppler_path: str | None = _resolve_poppler_path()

    def extract(
        self,
        pdf_path: str | Path,
        *,
        first_page: int | None = None,
        last_page: int | None = None,
        cache_dir: Path | None = None,
        dpi: int = 150,
    ) -> str:
        source = Path(pdf_path)
        text, page_count = self._extract_with_pdfplumber(
            source, first_page=first_page, last_page=last_page
        )
        logger.info(
            "pdfplumber extraction done",
            extra={"source": str(source), "pages_processed": page_count},
        )

        if len(text.strip()) < 100:
            logger.info(
                "Searchable text too short, falling back to OCR",
                extra={"source": str(source)},
            )
            text, ocr_page_count = self._extract_with_ocr(
                source,
                first_page=first_page,
                last_page=last_page,
                cache_dir=cache_dir,
                dpi=dpi,
            )
            logger.info(
                "OCR fallback done",
                extra={"source": str(source), "pages_processed": ocr_page_count},
            )

        if not text.strip():
            raise RuntimeError(f"No text extracted from PDF: {source}")

        return text

    # ------------------------------------------------------------------
    # pdfplumber extraction
    # ------------------------------------------------------------------

    def _extract_with_pdfplumber(
        self,
        path: Path,
        *,
        first_page: int | None = None,
        last_page: int | None = None,
    ) -> tuple[str, int]:
        try:
            import pdfplumber
        except ImportError as exc:
            raise RuntimeError("pdfplumber is required to parse PDF content") from exc

        with pdfplumber.open(str(path)) as pdf:
            total = len(pdf.pages)
            start = max((first_page or 1) - 1, 0)
            end = min(last_page or total, total)
            pages = []
            for page in pdf.pages[start:end]:
                extracted = page.extract_text(layout=True) or page.extract_text() or ""
                pages.append(extracted)
        return self.normalize_text("\n".join(pages)), end - start

    # ------------------------------------------------------------------
    # OCR fallback
    # ------------------------------------------------------------------

    def _extract_with_ocr(
        self,
        path: Path,
        *,
        first_page: int | None = None,
        last_page: int | None = None,
        cache_dir: Path | None = None,
        dpi: int = 150,
    ) -> tuple[str, int]:
        try:
            import pytesseract
        except ImportError as exc:
            raise RuntimeError(
                "OCR fallback requires 'pytesseract'. Install it with pip install pytesseract."
            ) from exc

        try:
            from pdf2image import convert_from_path, pdfinfo_from_path
        except ImportError as exc:
            raise RuntimeError(
                "OCR fallback requires 'pdf2image'. Install it with pip install pdf2image."
            ) from exc

        try:
            from PIL import ImageOps
        except ImportError as exc:
            raise RuntimeError(
                "OCR fallback requires 'Pillow'. Install it with pip install Pillow."
            ) from exc

        _check_poppler_available(self._poppler_path)

        poppler_kw: dict = {}
        if self._poppler_path:
            poppler_kw["poppler_path"] = self._poppler_path

        try:
            info = pdfinfo_from_path(str(path), **poppler_kw)
            total_pages = int(info.get("Pages", 0))
        except Exception as exc:
            raise RuntimeError(
                f"Could not read PDF page count from: {path}\n"
                f"  poppler_path={self._poppler_path or '(system PATH)'}\n"
                f"  Original error: {exc}\n"
                "Ensure poppler is installed and pdftoppm/pdfinfo are accessible."
            ) from exc

        if total_pages <= 0:
            raise RuntimeError(f"OCR fallback could not render pages from PDF: {path}")

        start = max((first_page or 1), 1)
        end = min((last_page or total_pages), total_pages)
        page_range = range(start, end + 1)
        pages_to_process = len(page_range)

        resolved_cache_dir = self.resolve_cache_dir(path, override=cache_dir)
        pdf_hash = self.compute_hash(path)

        from concurrent.futures import ThreadPoolExecutor

        max_workers = min(os.cpu_count() or 2, 4)

        def process_page(idx: int) -> str:
            cached = self._read_page_cache(resolved_cache_dir, pdf_hash, idx)
            if cached is not None:
                logger.debug("Cache hit for page %d", idx)
                return cached

            try:
                rendered = convert_from_path(
                    str(path), dpi=dpi, first_page=idx, last_page=idx, **poppler_kw
                )
                if not rendered:
                    return ""
                image = rendered[0]
                grayscale = ImageOps.grayscale(image)
                thresholded = grayscale.point(lambda x: 0 if x < 160 else 255, mode="1")
                text = pytesseract.image_to_string(thresholded) or ""
                image.close()
                grayscale.close()
                thresholded.close()

                self._write_page_cache(resolved_cache_dir, pdf_hash, idx, text)
                logger.info("OCR page %d/%d complete", idx, end)
                return text
            except Exception as e:
                logger.warning("Error on page %d: %s", idx, e)
                return ""

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            pages: list[str] = list(executor.map(process_page, page_range))

        merged_text = self.normalize_text("\n".join(pages))
        if not merged_text.strip():
            raise RuntimeError(f"OCR fallback returned no text for PDF: {path}")

        logger.info(
            "OCR complete: %d pages processed",
            pages_to_process,
        )
        return merged_text, pages_to_process

    # ------------------------------------------------------------------
    # Text normalization
    # ------------------------------------------------------------------

    def normalize_text(self, text: str) -> str:
        cleaned_lines: list[str] = []
        for raw_line in text.splitlines():
            line = re.sub(r"\s+", " ", raw_line).strip()
            if not line:
                continue
            if re.fullmatch(r"\d+", line):
                continue
            if (
                "copyright" in line.lower()
                or "cambridge university press" in line.lower()
            ):
                continue
            if line.lower().startswith("page "):
                continue
            if not cleaned_lines or cleaned_lines[-1] != line:
                cleaned_lines.append(line)
        return "\n".join(cleaned_lines)

    # ------------------------------------------------------------------
    # Hashing
    # ------------------------------------------------------------------

    @staticmethod
    def compute_hash(path: str | Path) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            while chunk := f.read(1 << 20):
                h.update(chunk)
        return h.hexdigest()[:16]

    # ------------------------------------------------------------------
    # OCR page cache
    # ------------------------------------------------------------------

    @staticmethod
    def resolve_cache_dir(path: str | Path, *, override: Path | None = None) -> Path:
        if override:
            return override
        env_dir = os.environ.get("OCR_CACHE_DIR")
        if env_dir:
            return Path(env_dir)
        return _DEFAULT_CACHE_DIR

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
