import hashlib
import json


def compute_content_hash(record: dict) -> str:
    """Deterministic hash of a structured record's fields (not raw HTML).

    Call this on the record *before* attaching the content_hash key itself, so the
    hash never includes its own value. Shared by every adapter that dual-writes a
    structured row alongside its chunk document (GOA-086, GOA-088).
    """
    canonical = json.dumps(record, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
