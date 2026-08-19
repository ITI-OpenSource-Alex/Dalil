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

KNOWN_NAMES = (
    "Tina", "Katsuharu", "Stephen", "Maxim", "Michal", "Hendrik",
    "Alexandra", "Aashish", "Monika", "Kopi", "Kenn", "Anuradha",
)

# Each candidate's transcript sits behind this marker in the page's accordions.
TRANSCRIPT_MARKER = "View transcript"

# A speaking response runs to hundreds of words across several turns. Anything
# much shorter is a fragment, and a fragment that gets scored becomes a
# reference text that scores low -- after which "the model is too harsh" is a
# conclusion we manufactured ourselves.
MIN_TRANSCRIPT_WORDS = 150
MIN_SPEAKER_TURNS = 4


def _candidates_from_manifest() -> list[dict]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    return [
        item for item in manifest["items"]
        if item["item_id"].startswith("ielts-official-")
    ]


def _strip_tags(fragment: str) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", fragment).split())


def segments(html: str) -> dict[str, str]:
    """Split the page into candidate name -> transcript text.

    Anchored on a structural marker rather than on candidate names.

    The first version of this matched a name and captured until the next name
    appeared. It failed silently and completely: the examiner opens by
    addressing the candidate -- "Examiner: Tina, now I'm going to give you a
    topic" -- so the terminator fired inside the first line and every transcript
    came out around fifty words long. The run reported 12 of 12 successful.

    Anchoring on structure removes that entire class of mistake, and _validate
    below is the backstop for whatever the next one turns out to be.
    """
    positions = [m.start() for m in re.finditer(re.escape(TRANSCRIPT_MARKER), html)]
    if not positions:
        return {}

    found: dict[str, str] = {}
    for index, start in enumerate(positions):
        end = positions[index + 1] if index + 1 < len(positions) else len(html)

        body = _strip_tags(html[start:end])

        # The candidate is named on both sides of the marker: in the heading
        # before it, and again in the examiner's opening line ("Examiner: Tina,
        # now I'm going to give you a topic"). Searching the heading alone found
        # nothing, because the page's markup puts more between the two than the
        # window covered. Searching both is what makes the mapping robust to the
        # page's layout rather than dependent on it.
        window = _strip_tags(html[max(0, start - 400):start]) + " " + body[:300]

        name = None
        for known in KNOWN_NAMES:
            if re.search(rf"\b{known}\b", window, re.IGNORECASE):
                name = known.lower()
                break
        if name is None or name in found:
            continue

        found[name] = body

    return found


def validate_transcript(text: str) -> str | None:
    """Return the problem with this transcript, or None if it is usable.

    Checked rather than assumed, because the failure mode is silent: a truncated
    transcript looks exactly like a successful extraction and only surfaces
    later as an inexplicably low score that reads like a finding about the
    model.
    """
    words = len(text.split())
    if words < MIN_TRANSCRIPT_WORDS:
        return f"only {words} words; a speaking response runs to hundreds"

    turns = len(re.findall(r"\b(?:Examiner|Candidate)\s*:", text))
    if turns < MIN_SPEAKER_TURNS:
        return f"only {turns} speaker turn(s); expected an exchange"

    return None


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

    by_name = segments(response.text)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    found: list[str] = []
    rejected: list[tuple[str, str]] = []

    for item in items:
        name = item["item_id"].removeprefix("ielts-official-")
        text = by_name.get(name)

        if text is None:
            rejected.append((name, "no transcript section found on the page"))
            continue

        problem = validate_transcript(text)
        if problem:
            # Refused, not written. A partial reference is worse than none: it
            # still produces a number, and the number is wrong in a direction
            # that looks like a finding.
            rejected.append((name, problem))
            continue

        destination = OUT_DIR / f"{item['item_id']}.txt"
        destination.write_text(text, encoding="utf-8")
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        found.append(name)

        print(
            f"  {item['item_id']:<28} band {item['labels']['overall_band']:<4} "
            f"{len(text.split()):>5} words  sha256 {digest}"
        )

    for name, problem in rejected:
        print(f"  {'ielts-official-' + name:<28} REJECTED: {problem}")

    print(f"\nwrote {len(found)} of {len(items)} transcripts to {OUT_DIR}")

    if rejected:
        print(
            f"\n{len(rejected)} item(s) were refused. Do not loosen the checks to "
            f"make them pass -- copy those sections in by hand, or leave them out. "
            f"A fragment that gets scored is worse than an item that is missing."
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
    return 0 if found else 1


if __name__ == "__main__":
    raise SystemExit(main())
