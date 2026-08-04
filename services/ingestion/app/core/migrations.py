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


def run_migrations(db_url: str | None = None) -> None:
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
                    executed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )
            for file_path in migration_files:
                filename = os.path.basename(file_path)
                cursor.execute(
                    "SELECT 1 FROM migrations_log WHERE migration_file = %s",
                    (filename,),
                )
                if cursor.fetchone():
                    continue

                sql = Path(file_path).read_text(encoding="utf-8").strip()
                if not sql:
                    continue
                cursor.execute(sql)
                cursor.execute(
                    "INSERT INTO migrations_log (migration_file) VALUES (%s)",
                    (filename,),
                )
        conn.commit()
