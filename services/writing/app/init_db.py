from pathlib import Path

from sqlalchemy import text

from app.database import engine
from app.models import CVReview, Essay  # noqa: F401


def run_migrations() -> None:
    migrations_dir = Path(__file__).resolve().parent.parent / "migrations"
    with engine.begin() as connection:
        for migration in sorted(migrations_dir.glob("*.sql")):
            connection.execute(text(migration.read_text(encoding="utf-8")))


if __name__ == "__main__":
    run_migrations()
    print("Writing service migrations applied successfully")
