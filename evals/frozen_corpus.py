"""Export and verify the fixed document corpus used by retrieval benchmarks.

The snapshot intentionally excludes embeddings: retrieval comparisons must keep the
same document facts and identifiers, while the embedding model/version is recorded in
the benchmark envelope.  JSONL is gzip-compressed with a fixed timestamp so identical
database contents produce byte-identical committed files.
"""

from __future__ import annotations

import argparse
import asyncio
import gzip
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Iterable

import asyncpg


DEFAULT_DB_URL = "postgresql://goa:goa_pass@localhost:5432/rag_db"
CORPUS_FIELDS = ("id", "title", "content", "source_url", "category")


def canonical_document_line(document: dict[str, Any]) -> bytes:
    """Return the stable bytes hashed by both the exporter and live harness."""

    canonical = {field: document.get(field) for field in CORPUS_FIELDS}
    canonical["id"] = str(canonical["id"])
    return (
        json.dumps(canonical, ensure_ascii=False, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def corpus_digest(documents: Iterable[dict[str, Any]]) -> tuple[int, str]:
    digest = hashlib.sha256()
    count = 0
    for document in documents:
        digest.update(canonical_document_line(document))
        count += 1
    return count, digest.hexdigest()


async def fetch_documents(database_url: str) -> list[dict[str, Any]]:
    connection = await asyncpg.connect(database_url)
    try:
        rows = await connection.fetch(
            """
            SELECT id, title, content, source_url, category
            FROM documents
            ORDER BY id
            """
        )
    finally:
        await connection.close()
    return [dict(row) for row in rows]


def write_snapshot(path: Path, documents: list[dict[str, Any]]) -> tuple[int, str]:
    path.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    with path.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as archive:
            for document in documents:
                line = canonical_document_line(document)
                archive.write(line)
                digest.update(line)
    return len(documents), digest.hexdigest()


def read_snapshot(path: Path) -> list[dict[str, Any]]:
    with gzip.open(path, "rt", encoding="utf-8") as archive:
        return [json.loads(line) for line in archive if line.strip()]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("--verify", action="store_true")
    parser.add_argument(
        "--database-url",
        default=os.environ.get("RAG_DATABASE_URL", DEFAULT_DB_URL),
    )
    args = parser.parse_args()

    live_documents = asyncio.run(fetch_documents(args.database_url))
    live_count, live_hash = corpus_digest(live_documents)

    if args.verify:
        snapshot_documents = read_snapshot(args.snapshot)
        snapshot_count, snapshot_hash = corpus_digest(snapshot_documents)
        matches = (live_count, live_hash) == (snapshot_count, snapshot_hash)
        print(
            json.dumps(
                {
                    "matches": matches,
                    "live": {"document_count": live_count, "content_hash": live_hash},
                    "snapshot": {
                        "document_count": snapshot_count,
                        "content_hash": snapshot_hash,
                    },
                },
                indent=2,
            )
        )
        return 0 if matches else 2

    count, content_hash = write_snapshot(args.snapshot, live_documents)
    print(
        json.dumps(
            {
                "snapshot": str(args.snapshot),
                "document_count": count,
                "content_hash": content_hash,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
