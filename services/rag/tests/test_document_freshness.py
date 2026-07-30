import asyncio
import uuid

import asyncpg
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app


def _run(coro):
    return asyncio.run(coro)


def test_delete_by_source_url_replaces_only_the_named_source():
    target_ids = [uuid.uuid4(), uuid.uuid4()]
    other_id = uuid.uuid4()
    source_url = "https://example.test/tiered-program"

    async def seed():
        conn = await asyncpg.connect(settings.database_url)
        try:
            await conn.execute(
                """
                INSERT INTO documents (id, content, source_url, category)
                VALUES ($1, 'tier one', $2, 'universities'),
                       ($3, 'tier two old', $2, 'universities'),
                       ($4, 'other', 'https://example.test/other', 'universities')
                """,
                target_ids[0],
                source_url,
                target_ids[1],
                other_id,
            )
        finally:
            await conn.close()

    async def count_rows():
        conn = await asyncpg.connect(settings.database_url)
        try:
            return (
                await conn.fetchval(
                    "SELECT COUNT(*) FROM documents WHERE source_url = $1", source_url
                ),
                await conn.fetchval(
                    "SELECT COUNT(*) FROM documents WHERE id = $1", other_id
                ),
            )
        finally:
            await conn.close()

    async def cleanup():
        conn = await asyncpg.connect(settings.database_url)
        try:
            await conn.execute(
                "DELETE FROM documents WHERE id = ANY($1::uuid[])",
                [*target_ids, other_id],
            )
        finally:
            await conn.close()

    try:
        _run(seed())
        with TestClient(app) as client:
            response = client.delete(
                "/internal/documents",
                params={"source_url": source_url},
                headers={"X-Internal-Api-Key": settings.internal_api_key},
            )
        assert response.status_code == 200
        assert response.json()["deleted"] == 2
        assert _run(count_rows()) == (0, 1)
    finally:
        _run(cleanup())


def test_document_upsert_reports_insert_then_update():
    document_id = uuid.uuid4()
    payload = {
        "documents": [
            {
                "id": str(document_id),
                "content": "first version",
                "embedding": [0.0] * 768,
                "source_url": "https://example.test/action-report",
                "category": "universities",
            }
        ]
    }

    async def cleanup():
        conn = await asyncpg.connect(settings.database_url)
        try:
            await conn.execute("DELETE FROM documents WHERE id = $1", document_id)
        finally:
            await conn.close()

    try:
        with TestClient(app) as client:
            first = client.post(
                "/internal/documents",
                json=payload,
                headers={"X-Internal-Api-Key": settings.internal_api_key},
            )
            payload["documents"][0]["content"] = "second version"
            second = client.post(
                "/internal/documents",
                json=payload,
                headers={"X-Internal-Api-Key": settings.internal_api_key},
            )

        assert first.status_code == 200
        assert first.json() == {
            "status": "success",
            "count": 1,
            "added": 1,
            "updated": 0,
        }
        assert second.status_code == 200
        assert second.json() == {
            "status": "success",
            "count": 1,
            "added": 0,
            "updated": 1,
        }
    finally:
        _run(cleanup())
