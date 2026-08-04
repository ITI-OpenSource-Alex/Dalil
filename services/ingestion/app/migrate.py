import os

from app.core.migrations import run_down_migrations, run_migrations


if __name__ == "__main__":
    if os.getenv("MIGRATION_DIRECTION") == "down":
        run_down_migrations()
    else:
        run_migrations()
