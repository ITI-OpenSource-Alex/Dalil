from pathlib import Path
import os

from sqlalchemy import text

from app.database import engine
from app.models import CVReview, Essay  # noqa: F401


# Any stable 64-bit key; shared by every process that migrates writing_db.
_MIGRATION_LOCK_ID = 20260725001


def run_migrations() -> None:
    """Apply the SQL migrations, serialised across processes.

    The `writing` service and the `cv-processor` container both run this against the
    same writing_db, and on a fresh volume they race: `CREATE TABLE IF NOT EXISTS` is
    NOT atomic against a concurrent creator, so both see the table missing, both
    create it, and the loser dies with

        duplicate key value violates unique constraint "pg_class_relname_nsp_index"

    which took the whole stack down (`dependency failed to start`). It never appears
    on an existing volume, because the tables are already there and the DDL is a
    no-op — a cold-start-only failure.

    The advisory lock is held for the duration of the transaction and released
    automatically on commit or rollback, so the second process simply waits and then
    finds the work already done.
    """
    migrations_dir = Path(__file__).resolve().parent.parent / "migrations"
    with engine.begin() as connection:
        connection.execute(text("SELECT pg_advisory_xact_lock(:key)"),
                           {"key": _MIGRATION_LOCK_ID})
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS migrations_log (
                migration_file VARCHAR(255) PRIMARY KEY,
                executed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                migration_batch_id VARCHAR(255)
            )
        """))
        connection.execute(text(
            "ALTER TABLE migrations_log ADD COLUMN IF NOT EXISTS migration_batch_id VARCHAR(255)"
        ))
        for migration in sorted(migrations_dir.glob("*.sql")):
            already_applied = connection.execute(
                text("SELECT 1 FROM migrations_log WHERE migration_file = :migration_file"),
                {"migration_file": migration.name},
            ).first()
            if already_applied:
                continue
            connection.execute(text(migration.read_text(encoding="utf-8")))
            connection.execute(
                text("""
                    INSERT INTO migrations_log (migration_file, migration_batch_id)
                    VALUES (:migration_file, :migration_batch_id)
                """),
                {
                    "migration_file": migration.name,
                    "migration_batch_id": os.getenv("MIGRATION_BATCH_ID"),
                },
            )


def run_down_migrations() -> None:
    batch_id = os.getenv("MIGRATION_BATCH_ID")
    if not batch_id:
        raise RuntimeError("MIGRATION_BATCH_ID is required for down migrations")

    migrations_dir = Path(__file__).resolve().parent.parent / "migrations"
    with engine.begin() as connection:
        connection.execute(text("SELECT pg_advisory_xact_lock(:key)"),
                           {"key": _MIGRATION_LOCK_ID})
        connection.execute(text(
            "ALTER TABLE migrations_log ADD COLUMN IF NOT EXISTS migration_batch_id VARCHAR(255)"
        ))
        rows = connection.execute(
            text("""
                SELECT migration_file
                FROM migrations_log
                WHERE migration_batch_id = :migration_batch_id
                ORDER BY migration_file DESC
            """),
            {"migration_batch_id": batch_id},
        )
        for row in rows:
            migration_file = row.migration_file
            rollback = migrations_dir / "rollback" / f"{Path(migration_file).stem}_down.sql"
            if not rollback.exists():
                raise RuntimeError(f"Missing rollback migration: {rollback}")
            connection.execute(text(rollback.read_text(encoding="utf-8")))
            connection.execute(
                text("DELETE FROM migrations_log WHERE migration_file = :migration_file"),
                {"migration_file": migration_file},
            )


if __name__ == "__main__":
    if os.getenv("MIGRATION_DIRECTION") == "down":
        run_down_migrations()
        print("Writing service migrations rolled back successfully")
    else:
        run_migrations()
        print("Writing service migrations applied successfully")
