import glob
import os
from pathlib import Path

import psycopg2


def _db_url() -> str:
    return (
        os.getenv("INGESTION_DATABASE_URL")
        or os.getenv("DATABASE_URL")
        or "postgresql://goa:goa_pass@localhost:5432/ingestion_db"
    )


def run_migrations(db_url: str | None = None, *, repair_existing: bool = False) -> None:
    migrations_dir = Path(__file__).resolve().parents[1] / "migrations"
    migration_files = sorted(glob.glob(str(migrations_dir / "*.sql")))
    if not migration_files:
        raise RuntimeError(f"No ingestion migrations found in {migrations_dir}")

    with psycopg2.connect(db_url or _db_url()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS migrations_log (
                    migration_file VARCHAR(255) PRIMARY KEY,
                    executed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    migration_batch_id VARCHAR(255)
                );
                """
            )
            cursor.execute(
                "ALTER TABLE migrations_log ADD COLUMN IF NOT EXISTS migration_batch_id VARCHAR(255)"
            )
            for file_path in migration_files:
                filename = os.path.basename(file_path)
                cursor.execute(
                    "SELECT 1 FROM migrations_log WHERE migration_file = %s",
                    (filename,),
                )
                already_executed = cursor.fetchone()
                if already_executed and not repair_existing:
                    continue

                sql = Path(file_path).read_text(encoding="utf-8").strip()
                if not sql:
                    continue
                cursor.execute(sql)
                if not already_executed:
                    cursor.execute(
                        "INSERT INTO migrations_log (migration_file, migration_batch_id) VALUES (%s, %s)",
                        (filename, os.getenv("MIGRATION_BATCH_ID")),
                    )
        conn.commit()


def run_down_migrations(db_url: str | None = None) -> None:
    batch_id = os.getenv("MIGRATION_BATCH_ID")
    if not batch_id:
        raise RuntimeError("MIGRATION_BATCH_ID is required for down migrations")

    migrations_dir = Path(__file__).resolve().parents[1] / "migrations"
    with psycopg2.connect(db_url or _db_url()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "ALTER TABLE migrations_log ADD COLUMN IF NOT EXISTS migration_batch_id VARCHAR(255)"
            )
            cursor.execute(
                """
                SELECT migration_file
                FROM migrations_log
                WHERE migration_batch_id = %s
                ORDER BY migration_file DESC
                """,
                (batch_id,),
            )
            for (filename,) in cursor.fetchall():
                stem = Path(filename).stem
                rollback_path = migrations_dir / "rollback" / f"{stem}_down.sql"
                if not rollback_path.exists():
                    raise RuntimeError(f"Missing rollback migration: {rollback_path}")

                sql = rollback_path.read_text(encoding="utf-8").strip()
                if not sql:
                    continue
                cursor.execute(sql)
                cursor.execute(
                    "DELETE FROM migrations_log WHERE migration_file = %s",
                    (filename,),
                )
        conn.commit()
