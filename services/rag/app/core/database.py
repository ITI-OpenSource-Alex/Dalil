import os
import glob
import logging
import asyncpg
from pgvector.asyncpg import register_vector
from app.core.config import settings

logger = logging.getLogger("rag_service.database")


class Database:
    def __init__(self):
        self.pool = None

    async def connect(self):
        if not self.pool:
            logger.info("Initializing asyncpg connection pool...")
            # Run migrations first using a direct connection (no vector init)
            await self.run_migrations()

            self.pool = await asyncpg.create_pool(
                dsn=settings.database_url,
                min_size=2,
                max_size=10,
                init=register_vector
            )

    async def disconnect(self):
        if self.pool:
            logger.info("Closing asyncpg connection pool...")
            await self.pool.close()
            self.pool = None

    async def run_migrations(self):
        logger.info("Starting database migrations...")
        conn = await asyncpg.connect(settings.database_url)
        try:
            # Create migrations_log table if it doesn't exist
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS migrations_log (
                    migration_file VARCHAR(255) PRIMARY KEY,
                    executed_at TIMESTAMP DEFAULT NOW(),
                    migration_batch_id VARCHAR(255)
                );
            """)
            await conn.execute(
                "ALTER TABLE migrations_log ADD COLUMN IF NOT EXISTS migration_batch_id VARCHAR(255)"
            )

            # Find all migration files in migrations directory
            current_dir = os.path.dirname(os.path.abspath(__file__))
            # migrations directory is in app/migrations (parent of app/core)
            migrations_dir = os.path.join(os.path.dirname(current_dir), "migrations")
            migration_files = sorted(glob.glob(os.path.join(migrations_dir, "*.sql")))

            if not migration_files:
                logger.warning("No migration files found in %s", migrations_dir)
                return

            for file_path in migration_files:
                filename = os.path.basename(file_path)

                # Check if migration was already executed
                already_executed = await conn.fetchval(
                    "SELECT 1 FROM migrations_log WHERE migration_file = $1", filename
                )

                if not already_executed:
                    logger.info("Executing migration: %s", filename)
                    with open(file_path, "r", encoding="utf-8") as f:
                        sql = f.read()

                    # An empty (or comment-only) migration file makes asyncpg return None
                    # for the statement, and the driver then raises
                    # "AttributeError: 'NoneType' object has no attribute 'decode'",
                    # aborting startup entirely. (This exact bug crash-looped the Exam
                    # service via its empty 005_seed_writing_questions.sql.) Skip it
                    # WITHOUT recording it as applied, so it still runs once real SQL
                    # is added — placeholder migration files are normal in this project.
                    if not sql.strip():
                        logger.warning(
                            "Migration %s is empty — skipping (not marked as applied)",
                            filename,
                        )
                        continue

                    # Run migration in a transaction block
                    async with conn.transaction():
                        await conn.execute(sql)
                        await conn.execute(
                            "INSERT INTO migrations_log (migration_file, migration_batch_id) VALUES ($1, $2)",
                            filename,
                            os.getenv("MIGRATION_BATCH_ID"),
                        )
                    logger.info("Migration %s executed successfully", filename)
                else:
                    logger.debug("Migration %s already executed, skipping", filename)
        finally:
            await conn.close()

    async def run_down_migrations(self):
        batch_id = os.getenv("MIGRATION_BATCH_ID")
        if not batch_id:
            raise RuntimeError("MIGRATION_BATCH_ID is required for down migrations")

        conn = await asyncpg.connect(settings.database_url)
        try:
            await conn.execute(
                "ALTER TABLE migrations_log ADD COLUMN IF NOT EXISTS migration_batch_id VARCHAR(255)"
            )
            current_dir = os.path.dirname(os.path.abspath(__file__))
            migrations_dir = os.path.join(os.path.dirname(current_dir), "migrations")
            migration_files = await conn.fetch(
                """
                SELECT migration_file
                FROM migrations_log
                WHERE migration_batch_id = $1
                ORDER BY migration_file DESC
                """,
                batch_id,
            )

            for row in migration_files:
                filename = row["migration_file"]
                stem, _ = os.path.splitext(filename)
                rollback_path = os.path.join(migrations_dir, "rollback", f"{stem}_down.sql")
                if not os.path.exists(rollback_path):
                    raise RuntimeError(f"Missing rollback migration: {rollback_path}")

                with open(rollback_path, "r", encoding="utf-8") as f:
                    sql = f.read().strip()
                if not sql:
                    continue

                async with conn.transaction():
                    await conn.execute(sql)
                    await conn.execute(
                        "DELETE FROM migrations_log WHERE migration_file = $1",
                        filename,
                    )
                logger.info("Migration %s rolled back successfully", filename)
        finally:
            await conn.close()

db = Database()
