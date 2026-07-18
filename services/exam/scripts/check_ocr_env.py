"""
OCR Environment Diagnostic
===========================
Checks that all OCR dependencies are installed and working.

Usage::

    python scripts/check_ocr_env.py
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys

PASS = "✓"
FAIL = "✗"

passed = 0
failed = 0


def check(label: str, ok: bool, detail: str) -> None:
    global passed, failed
    if ok:
        passed += 1
        print(f"  {PASS} {label}: {detail}")
    else:
        failed += 1
        print(f"  {FAIL} {label}: {detail}")


def run_version(cmd: list[str]) -> str | None:
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=10,
        )
        output = (result.stdout or result.stderr or "").strip()
        return output.splitlines()[0] if output else None
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


def main() -> int:
    global passed, failed

    print("=" * 60)
    print("OCR ENVIRONMENT DIAGNOSTIC")
    print("=" * 60)
    print(f"  Platform: {platform.system()} {platform.release()}")
    print(f"  Python:   {sys.version.split()[0]}")
    print()

    # ---- Poppler ----
    print("--- Poppler (pdf2image backend) ---")

    poppler_path = os.environ.get("POPPLER_PATH")
    if poppler_path:
        print(f"  POPPLER_PATH = {poppler_path}")
        check("POPPLER_PATH dir exists", os.path.isdir(poppler_path), poppler_path)
    else:
        print("  POPPLER_PATH = (not set)")

    pdftoppm_bin = None
    if poppler_path:
        for name in ("pdftoppm", "pdftoppm.exe"):
            candidate = os.path.join(poppler_path, name)
            if os.path.isfile(candidate):
                pdftoppm_bin = candidate
                break
    if not pdftoppm_bin:
        pdftoppm_bin = shutil.which("pdftoppm")

    pdfinfo_bin = None
    if poppler_path:
        for name in ("pdfinfo", "pdfinfo.exe"):
            candidate = os.path.join(poppler_path, name)
            if os.path.isfile(candidate):
                pdfinfo_bin = candidate
                break
    if not pdfinfo_bin:
        pdfinfo_bin = shutil.which("pdfinfo")

    if pdftoppm_bin:
        ver = run_version([pdftoppm_bin, "-v"])
        check("pdftoppm", True, f"{pdftoppm_bin} ({ver})")
    else:
        check("pdftoppm", False, "NOT FOUND in PATH or POPPLER_PATH")

    if pdfinfo_bin:
        ver = run_version([pdfinfo_bin, "-v"])
        check("pdfinfo", True, f"{pdfinfo_bin} ({ver})")
    else:
        check("pdfinfo", False, "NOT FOUND in PATH or POPPLER_PATH")

    print()

    # ---- Tesseract ----
    print("--- Tesseract ---")

    tesseract_bin = shutil.which("tesseract")
    if tesseract_bin:
        ver = run_version([tesseract_bin, "--version"])
        check("tesseract", True, f"{tesseract_bin} ({ver})")
    else:
        check("tesseract", False, "NOT FOUND in PATH")

    print()

    # ---- Python packages ----
    print("--- Python packages ---")

    try:
        import pdfplumber
        check("pdfplumber", True, pdfplumber.__version__)
    except ImportError:
        check("pdfplumber", False, "not installed (pip install pdfplumber)")

    try:
        import pytesseract
        tess_cmd = pytesseract.pytesseract.tesseract_cmd
        check("pytesseract", True, f"{pytesseract.__version__} (cmd={tess_cmd})")
    except ImportError:
        check("pytesseract", False, "not installed (pip install pytesseract)")

    try:
        import pdf2image
        from importlib.metadata import version
        check("pdf2image", True, version("pdf2image"))
    except ImportError:
        check("pdf2image", False, "not installed (pip install pdf2image)")

    try:
        from PIL import Image
        import PIL
        check("Pillow", True, PIL.__version__)
    except ImportError:
        check("Pillow", False, "not installed (pip install Pillow)")

    print()

    # ---- OcrService ----
    print("--- OcrService integration ---")

    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    try:
        from app.ingestion.ocr_service import OcrService, _resolve_poppler_path
        resolved = _resolve_poppler_path()
        check("OcrService imports", True, f"poppler_path={resolved or '(system PATH)'}")
    except Exception as e:
        check("OcrService imports", False, str(e))

    print()

    # ---- Live pdf2image test ----
    print("--- Live pdf2image test (single-page render) ---")

    try:
        from pdf2image import convert_from_path
        import tempfile

        # Create a minimal valid PDF to test poppler
        pdf_bytes = (
            b"%PDF-1.0\n1 0 obj<</Pages 2 0 R>>endobj\n"
            b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
            b"3 0 obj<</Type/Page/MediaBox[0 0 72 72]/Parent 2 0 R>>endobj\n"
            b"xref\n0 4\n0000000000 65535 f \n"
            b"0000000009 00000 n \n0000000043 00000 n \n0000000098 00000 n \n"
            b"trailer<</Root 1 0 R/Size 4>>\nstartxref\n167\n%%EOF"
        )
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(pdf_bytes)
            tmp_path = tmp.name

        kw = {}
        if resolved:
            kw["poppler_path"] = resolved
        images = convert_from_path(tmp_path, dpi=72, first_page=1, last_page=1, **kw)
        os.unlink(tmp_path)

        if images:
            w, h = images[0].size
            images[0].close()
            check("pdf2image render", True, f"rendered 1 page ({w}x{h}px)")
        else:
            check("pdf2image render", False, "convert_from_path returned empty list")
    except Exception as e:
        check("pdf2image render", False, str(e))
        try:
            os.unlink(tmp_path)
        except Exception:
            pass

    # ---- Summary ----
    print()
    print("=" * 60)
    print(f"  Passed: {passed}")
    print(f"  Failed: {failed}")
    print("=" * 60)

    if failed:
        print()
        if not pdftoppm_bin:
            print("FIX: Install poppler:")
            if platform.system() == "Windows":
                print("  1. Download from https://github.com/oschwartz10612/poppler-windows/releases")
                print("  2. Extract to C:\\tools\\poppler\\")
                print("  3. Set POPPLER_PATH=C:\\tools\\poppler\\Library\\bin")
            elif platform.system() == "Darwin":
                print("  brew install poppler")
            else:
                print("  apt-get install poppler-utils  OR  apk add poppler-utils")
        if not tesseract_bin:
            print("FIX: Install tesseract:")
            if platform.system() == "Windows":
                print("  Download from https://github.com/UB-Mannheim/tesseract/wiki")
            elif platform.system() == "Darwin":
                print("  brew install tesseract")
            else:
                print("  apt-get install tesseract-ocr  OR  apk add tesseract-ocr")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
