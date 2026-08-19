import glob
import json
import logging
import os

import asyncpg

from app.core.config import settings

logger = logging.getLogger("exam_service.database")


class Database:
    def __init__(self):
        self.pool = None

    async def connect(self):
        if not self.pool:
            logger.info("Initializing asyncpg connection pool...")
            self.pool = await asyncpg.create_pool(
                dsn=settings.database_url, min_size=2, max_size=10
            )
            await self.run_migrations()
            await self.seed_band_tables()

    async def disconnect(self):
        if self.pool:
            logger.info("Closing asyncpg connection pool...")
            await self.pool.close()
            self.pool = None

    async def run_migrations(self):
        logger.info("Starting database migrations...")
        async with self.pool.acquire() as conn:
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

            current_dir = os.path.dirname(os.path.abspath(__file__))
            migrations_dir = os.path.join(os.path.dirname(current_dir), "migrations")
            migration_files = sorted(glob.glob(os.path.join(migrations_dir, "*.sql")))

            if not migration_files:
                logger.warning("No migration files found in %s", migrations_dir)
                return

            for file_path in migration_files:
                filename = os.path.basename(file_path)
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
                    # which aborts startup entirely. Skip it WITHOUT recording it as
                    # applied, so it still runs once real SQL is added to the file.
                    if not sql.strip():
                        logger.warning(
                            "Migration %s is empty — skipping (not marked as applied)",
                            filename,
                        )
                        continue

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

    async def run_down_migrations(self):
        batch_id = os.getenv("MIGRATION_BATCH_ID")
        if not batch_id:
            raise RuntimeError("MIGRATION_BATCH_ID is required for down migrations")

        if not self.pool:
            self.pool = await asyncpg.create_pool(
                dsn=settings.database_url, min_size=1, max_size=2
            )

        async with self.pool.acquire() as conn:
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

    async def seed_band_tables(self):
        seeds = [
            {
                "skill_area": "reading",
                "exam_type": "academic",
                "conversion": [
                    [39, 9.0],
                    [37, 8.5],
                    [35, 8.0],
                    [33, 7.5],
                    [30, 7.0],
                    [27, 6.5],
                    [23, 6.0],
                    [19, 5.5],
                    [15, 5.0],
                    [13, 4.5],
                    [10, 4.0],
                    [6, 3.5],
                    [4, 3.0],
                    [3, 2.5],
                    [2, 2.0],
                    [0, 0.0],
                ],
            },
            {
                "skill_area": "reading",
                "exam_type": "general",
                "conversion": [
                    [40, 9.0],
                    [39, 8.5],
                    [37, 8.0],
                    [36, 7.5],
                    [34, 7.0],
                    [32, 6.5],
                    [30, 6.0],
                    [27, 5.5],
                    [23, 5.0],
                    [19, 4.5],
                    [15, 4.0],
                    [12, 3.5],
                    [9, 3.0],
                    [6, 2.5],
                    [3, 2.0],
                    [0, 0.0],
                ],
            },
        ]
        async with self.pool.acquire() as conn:
            for seed in seeds:
                exists = await conn.fetchval(
                    "SELECT 1 FROM band_conversion_tables "
                    "WHERE skill_area=$1 AND exam_type=$2",
                    seed["skill_area"],
                    seed["exam_type"],
                )
                if not exists:
                    await conn.execute(
                        "INSERT INTO band_conversion_tables "
                        "(skill_area, exam_type, conversion) "
                        "VALUES ($1, $2, $3::jsonb)",
                        seed["skill_area"],
                        seed["exam_type"],
                        json.dumps(seed["conversion"]),
                    )
                    logger.info(
                        "Seeded band table: %s/%s",
                        seed["skill_area"],
                        seed["exam_type"],
                    )


db = Database()
