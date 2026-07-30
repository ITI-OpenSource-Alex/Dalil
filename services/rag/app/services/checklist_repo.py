import json
from typing import Any

from app.core.database import db


def _row_to_checklist(row) -> dict[str, Any]:
    """asyncpg returns JSONB columns as raw text (no codec is registered for it,
    unlike vector -- see app/core/database.py's register_vector), so `items` has to
    be decoded here rather than at every call site."""
    items = row["items"]
    if isinstance(items, str):
        items = json.loads(items)
    return {
        "id": row["id"],
        "program_id": row["program_id"],
        "items": items,
        "generated_by": row["generated_by"],
    }


async def get_checklist(user_id: str, program_id: str) -> dict[str, Any] | None:
    """Fetch the persisted checklist for (user_id, program_id), or None if absent."""
    async with db.pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, program_id, items, generated_by
            FROM checklists
            WHERE user_id = $1 AND program_id = $2
            """,
            user_id,
            program_id,
        )
    return _row_to_checklist(row) if row else None


async def create_checklist(
    user_id: str,
    program_id: str,
    title: str,
    items: list[dict[str, Any]],
    generated_by: str,
) -> dict[str, Any]:
    """Persist a freshly generated checklist, or return the checklist a concurrent
    request already created.

    `uq_checklists_user_program` (migration 027) plus ON CONFLICT DO NOTHING is what
    makes this race-safe: only one caller's INSERT ever lands, and a losing caller
    gets no RETURNING row back, falling through to the re-select below -- which
    returns the winner's checklist rather than erroring.
    """
    items_json = json.dumps(items)
    async with db.pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                """
                INSERT INTO checklists (program_id, user_id, title, items, generated_by)
                VALUES ($1, $2, $3, $4::jsonb, $5)
                ON CONFLICT (user_id, program_id) DO NOTHING
                RETURNING id, program_id, items, generated_by
                """,
                program_id,
                user_id,
                title,
                items_json,
                generated_by,
            )
            if row is None:
                row = await conn.fetchrow(
                    """
                    SELECT id, program_id, items, generated_by
                    FROM checklists
                    WHERE user_id = $1 AND program_id = $2
                    """,
                    user_id,
                    program_id,
                )
    return _row_to_checklist(row)


async def get_item_states(checklist_id) -> dict[str, bool]:
    async with db.pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT item_key, is_checked FROM checklist_item_states WHERE checklist_id = $1",
            checklist_id,
        )
    return {row["item_key"]: row["is_checked"] for row in rows}


async def upsert_item_state(checklist_id, item_key: str, is_checked: bool, user_id: str) -> None:
    async with db.pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO checklist_item_states (checklist_id, user_id, item_key, is_checked)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (checklist_id, item_key) DO UPDATE
            SET is_checked = EXCLUDED.is_checked,
                updated_at = NOW()
            """,
            checklist_id,
            user_id,
            item_key,
            is_checked,
        )
