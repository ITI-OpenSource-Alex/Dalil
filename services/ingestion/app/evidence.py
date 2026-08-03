import unicodedata
from typing import Any
from pydantic import BaseModel

IDENTITY_FIELDS = {
    "source_id", "country", "visa_type", "issuing_body",
    "source_url", "extraction_valid", "content_hash", "extraction_evidence"
}

def normalize_whitespace(text: str) -> str:
    """Collapses NFKC unicode variations, normalizes curly quotes/apostrophes, and collapses whitespace into a single space."""
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    return " ".join(text.split())

def get_non_null_leaf_paths(obj: Any, prefix: str = "") -> dict[str, str]:
    """
    Recursively builds a dictionary mapping JSON dot-notation paths to string representations
    for all non-null leaf fields, excluding identity metadata fields.
    """
    leaf_paths: dict[str, str] = {}

    if isinstance(obj, BaseModel):
        obj = obj.model_dump()

    if isinstance(obj, dict):
        for k, v in obj.items():
            if not prefix and k in IDENTITY_FIELDS:
                continue
            if v is None:
                continue
            path = f"{prefix}.{k}" if prefix else str(k)
            leaf_paths.update(get_non_null_leaf_paths(v, prefix=path))

    elif isinstance(obj, list):
        for idx, item in enumerate(obj):
            if item is None:
                continue
            path = f"{prefix}[{idx}]"
            leaf_paths.update(get_non_null_leaf_paths(item, prefix=path))

    elif obj is not None:
        val_str = str(obj).strip()
        if val_str and prefix:
            leaf_paths[prefix] = val_str

    return leaf_paths


def validate_evidence(outcome: BaseModel, original_text: str) -> None:
    """
    Validates that every non-null leaf field has a verbatim evidence quote in original_text,
    keyed by its JSON path, and that no orphan evidence keys exist. Whitespace runs in quotes
    and original_text are normalized before matching.
    """
    expected_map = get_non_null_leaf_paths(outcome)
    evidence_map = getattr(outcome, "extraction_evidence", None)
    if evidence_map is None:
        evidence_map = {}

    # 1. Per-leaf coverage check
    for path in expected_map:
        if path not in evidence_map or not str(evidence_map[path]).strip():
            raise ValueError(f"Missing evidence entry for leaf field '{path}'")

    # 2. Orphan evidence key check
    for key in evidence_map:
        if key not in expected_map:
            raise ValueError(f"Orphan evidence key '{key}' has no corresponding extracted leaf field")

    # 3. Verbatim case-sensitive match & quote length check with whitespace normalization
    normalized_source = normalize_whitespace(original_text)
    for key, quote in evidence_map.items():
        quote_str = str(quote).strip()
        if len(quote_str.split()) > 20:
            raise ValueError(f"Evidence quote for '{key}' exceeds 20 words: '{quote_str}'")

        normalized_quote = normalize_whitespace(quote_str)
        if normalized_quote not in normalized_source:
            raise ValueError(f"Evidence quote for '{key}' not found verbatim in source text: '{quote_str}'")
