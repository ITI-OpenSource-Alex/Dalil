import io
import zipfile
from pathlib import PurePosixPath

import pdfplumber
from docx import Document


class UnsupportedCVType(ValueError):
    """Raised when an S3 object is not an extractable CV format."""


def detect_file_type(s3_key: str, content_type: str | None = None) -> str:
    extension = PurePosixPath(s3_key).suffix.lower()
    if extension == ".pdf" and content_type in {
        None,
        "",
        "application/pdf",
        "application/octet-stream",
    }:
        return "pdf"
    if extension == ".docx" and content_type in {
        None,
        "",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/octet-stream",
    }:
        return "docx"
    raise UnsupportedCVType("Only PDF and DOCX CV files can be processed")


def extract_plain_text(file_bytes: bytes, file_type: str) -> str:
    if file_type == "pdf":
        text = _extract_pdf(file_bytes)
    elif file_type == "docx":
        text = _extract_docx(file_bytes)
    else:
        raise UnsupportedCVType(f"Unsupported CV file type: {file_type}")

    normalized = "\n".join(line.rstrip() for line in text.splitlines()).strip()
    if not normalized:
        raise ValueError("The CV did not contain extractable text")
    return normalized


def _extract_pdf(file_bytes: bytes) -> str:
    if not file_bytes.startswith(b"%PDF-"):
        raise ValueError("The object does not contain a valid PDF signature")
    try:
        with pdfplumber.open(io.BytesIO(file_bytes)) as document:
            return "\n".join(page.extract_text() or "" for page in document.pages)
    except Exception as exc:
        raise ValueError("The PDF could not be parsed") from exc


def _extract_docx(file_bytes: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(file_bytes)) as archive:
            if "word/document.xml" not in archive.namelist():
                raise ValueError("The object is not a DOCX document")
        document = Document(io.BytesIO(file_bytes))
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        raise ValueError("The DOCX file could not be parsed") from exc

    parts = [paragraph.text for paragraph in document.paragraphs if paragraph.text.strip()]
    for table in document.tables:
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
            if cells:
                parts.append(" | ".join(cells))
    return "\n".join(parts)
