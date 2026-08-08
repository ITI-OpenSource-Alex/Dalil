"""Fetch the official IELTS speaking sample transcripts into a local directory.

SPEAK-EVAL-007. The 12 samples on ielts.org carry examiner-assigned overall
bands across 5.0-9.0 -- the only gold-standard speaking labels this project has
access to.

Two rules govern this script, and both are about what does NOT happen.

**The transcripts are never committed.** They are published by the IELTS
Partners under a general copyright notice with no stated reuse permission. The
*band score* is a fact and lives in the manifest; the *wording* is expression
and lives only on the machine that runs the eval, in a gitignored directory.
That distinction is the whole reason this is a fetch script rather than a data
file.

**Permission is not decided here.** Every item stays `permission.status:
pending` until a human reads the terms and records the decision. This script
prints the hash you need to complete the manifest entry; it does not promote
anything, and running it grants nothing. Under rule 1 of the manifest
validators, a `pending` item cannot gate, so a forgotten review fails closed.

    python evals/speaking/fetch_official_samples.py

Writes to evals/speaking/official/ (gitignored). Requires network.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT_DIR = HERE / "official"
MANIFEST = HERE / "manifest" / "manifest.json"

SOURCE_URL = (
    "https://ielts.org/organisations/ielts-for-organisations/"
    "understanding-ielts-scoring/resources-for-setting-your-ielts-scores"
)


def _candidates_from_manifest() -> list[dict]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    return [
        item for item in manifest["items"]
        if item["item_id"].startswith("ielts-official-")
    ]


def _extract(page_text: str, name: str) -> str | None:
    """Pull one candidate's section out of the page text.

    Deliberately conservative: it returns None rather than a guess when the
    section cannot be located unambiguously. A silently truncated transcript
    would become a reference text that scores lower than it should, and the
    resulting 'the model is too harsh' conclusion would be entirely our own
    doing.
    """
    pattern = re.compile(
        rf"\b{re.escape(name)}\b(.{{200,}}?)(?=\b(?:Tina|Katsuharu|Stephen|Maxim|"
        rf"Michal|Hendrik|Alexandra|Aashish|Monika|Kopi|Kenn|Anuradha)\b|\Z)",
        re.IGNORECASE | re.DOTALL,
    )
    match = pattern.search(page_text)
    if not match:
        return None
    text = " ".join(match.group(1).split())
    return text if len(text) >= 200 else None


def main() -> int:
    try:
        import httpx
    except ImportError:
        print("httpx is required: pip install httpx", file=sys.stderr)
        return 2

    items = _candidates_from_manifest()
    if not items:
        print("no ielts-official-* items in the manifest", file=sys.stderr)
        return 2

    print(f"source: {SOURCE_URL}")
    print(
        "\nNOTE: this downloads copyrighted material to a gitignored local\n"
        "directory for internal evaluation. It does not grant permission and it\n"
        "does not promote any item. Review the terms yourself before setting\n"
        "permission.status to `granted`.\n"
    )

    try:
        response = httpx.get(SOURCE_URL, timeout=60.0, follow_redirects=True)
        response.raise_for_status()
    except Exception as exc:
        print(f"could not fetch the page: {exc}", file=sys.stderr)
        return 1

    page_text = re.sub(r"<[^>]+>", " ", response.text)
    page_text = re.sub(r"\s+", " ", page_text)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    found, missing = 0, []

    for item in items:
        name = item["item_id"].removeprefix("ielts-official-")
        text = _extract(page_text, name)
        if text is None:
            missing.append(name)
            continue

        destination = OUT_DIR / f"{item['item_id']}.txt"
        destination.write_text(text, encoding="utf-8")
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        found += 1

        print(
            f"  {item['item_id']:<28} band {item['labels']['overall_band']:<4} "
            f"{len(text.split()):>5} words  sha256 {digest}"
        )

    print(f"\nwrote {found} of {len(items)} transcripts to {OUT_DIR}")

    if missing:
        print(
            f"\ncould not locate: {', '.join(missing)}.\n"
            f"The page structure has probably changed. Copy those sections in by\n"
            f"hand rather than loosening the matcher -- a truncated transcript\n"
            f"becomes a reference that scores low, and the 'model is too harsh'\n"
            f"conclusion would be our own doing."
        )

    print(
        "\nTo make these usable:\n"
        "  1. Read the IELTS terms of use and decide whether this use is permitted.\n"
        "  2. If it is, set permission.status to `granted` with reviewed_by and\n"
        "     reviewed_at, and paste each sha256 into transcript.sha256.\n"
        "  3. Move the items to the `smoke` split.\n"
        "  4. Run: python evals/speaking/manifest/validate.py\n"
        "Until step 2, these items cannot gate anything, which is intended."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
