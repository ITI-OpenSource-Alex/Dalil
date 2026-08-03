from pathlib import Path

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
        for migration in sorted(migrations_dir.glob("*.sql")):
            connection.execute(text(migration.read_text(encoding="utf-8")))


if __name__ == "__main__":
    run_migrations()
    print("Writing service migrations applied successfully")
