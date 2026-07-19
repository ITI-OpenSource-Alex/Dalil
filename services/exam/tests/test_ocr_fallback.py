from __future__ import annotations

import builtins
from pathlib import Path
from typing import Any

import pytest

from app.ingestion.parser import BaseParser
from app.ingestion.ocr_service import OcrService


class DummyParser(BaseParser):
    def __init__(self) -> None:
        super().__init__()
        self.last_content = ""

    def parse_text(self, content: str | Path) -> dict[str, str]:
        self.last_content = str(content)
        return {"raw": self.last_content}


def test_parse_pdf_uses_pdfplumber_when_text_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parser = DummyParser()

    monkeypatch.setattr(
        parser._ocr_service,
        "extract",
        lambda _path, **kw: "PDF searchable text " * 10,
    )

    result = parser.parse_pdf("sample.pdf")
    assert "PDF searchable text" in result["raw"]


def test_parse_pdf_falls_back_to_ocr_when_pdfplumber_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parser = DummyParser()

    monkeypatch.setattr(
        parser._ocr_service,
        "extract",
        lambda _path, **kw: "OCR Cambridge text",
    )

    result = parser.parse_pdf("sample.pdf")

    assert "OCR Cambridge text" in result["raw"]
    assert parser.last_content.startswith("sample.pdf")


def test_parse_pdf_raises_when_ocr_returns_no_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parser = DummyParser()

    def fake_extract(_path, **kw):
        raise RuntimeError("No text extracted from PDF: sample.pdf")

    monkeypatch.setattr(parser._ocr_service, "extract", fake_extract)

    with pytest.raises(RuntimeError, match="No text extracted from PDF"):
        parser.parse_pdf("sample.pdf")


def test_ocr_missing_pytesseract_raises_descriptive_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = OcrService()

    original_import = builtins.__import__

    def fake_import(name: str, *args, **kwargs):
        if name == "pytesseract":
            raise ImportError("No module named pytesseract")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(RuntimeError, match="requires 'pytesseract'"):
        service._extract_with_ocr(Path("sample.pdf"))


def test_page_range_params_propagate(monkeypatch: pytest.MonkeyPatch) -> None:
    """parse_pdf passes first_page/last_page through to OcrService.extract."""
    parser = DummyParser()
    captured: dict[str, Any] = {}

    def fake_extract(_path, *, first_page=None, last_page=None, **kw):
        captured["first_page"] = first_page
        captured["last_page"] = last_page
        return "Enough text to skip OCR " * 10

    monkeypatch.setattr(parser._ocr_service, "extract", fake_extract)

    parser.parse_pdf("sample.pdf", first_page=3, last_page=7)

    assert captured["first_page"] == 3
    assert captured["last_page"] == 7


def test_ocr_cache_write_and_read(tmp_path: Path) -> None:
    """OCR cache round-trips page text correctly."""
    pdf_hash = "abc123deadbeef00"
    OcrService._write_page_cache(tmp_path, pdf_hash, 5, "Hello OCR text")
    result = OcrService._read_page_cache(tmp_path, pdf_hash, 5)
    assert result == "Hello OCR text"


def test_ocr_cache_miss_returns_none(tmp_path: Path) -> None:
    """Missing cache entry returns None, not an error."""
    result = OcrService._read_page_cache(tmp_path, "nonexistent", 1)
    assert result is None


def test_compute_pdf_hash_is_deterministic(tmp_path: Path) -> None:
    """Same file content always produces the same hash."""
    pdf = tmp_path / "test.pdf"
    pdf.write_bytes(b"fake pdf content for hashing")

    h1 = OcrService.compute_hash(pdf)
    h2 = OcrService.compute_hash(pdf)
    assert h1 == h2
    assert len(h1) == 16


def test_normalize_text_preserves_repeated_headers() -> None:
    """Ensure that identical headers separated by other text are NOT deduplicated."""
    service = OcrService()
    raw_text = """
READING PASSAGE 1
Some random text for test 1
More text...
READING PASSAGE 1
Some random text for test 2
More text...
"""
    normalized = service.normalize_text(raw_text)
    # The header should appear exactly twice.
    assert normalized.count("READING PASSAGE 1") == 2
    assert "Some random text for test 1" in normalized
    assert "Some random text for test 2" in normalized


def test_normalize_text_removes_consecutive_duplicates() -> None:
    """Ensure that identical consecutive lines ARE deduplicated."""
    service = OcrService()
    raw_text = """
READING PASSAGE 1
READING PASSAGE 1
Some random text
"""
    normalized = service.normalize_text(raw_text)
    # The consecutive duplicate should be removed.
    assert normalized.count("READING PASSAGE 1") == 1
    assert "Some random text" in normalized
