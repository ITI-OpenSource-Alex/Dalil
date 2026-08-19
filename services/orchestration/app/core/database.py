"""Postgres access for the Orchestration service.

This is the service's first database code. `DATABASE_URL` has been configured
since GOA-001 and `orchestration_db` has existed since the compose file was
written, but nothing ever connected to either -- session state lived entirely in
Redis. GOA-038's long-term facts are the first thing that needs to outlive a
24-hour Redis TTL.

Ported from `services/rag/app/core/database.py`, minus pgvector. The migration
runner and its `migrations_log` bookkeeping are deliberately identical to RAG's
and Exam's, so all three services fail and recover the same way.
"""

import glob
import os

import asyncpg
import structlog

from app.core.config import settings

logger = structlog.get_logger("orchestration.database")


class Database:
    def __init__(self):
        self.pool = None
        # Read by /health. A service that reports healthy while every write
        # 500s is worse than one that reports degraded: the first is silent.
        self.migrations_applied = 0

    async def connect(self):
        if not self.pool:
            logger.info("Initializing asyncpg connection pool...")
            # Migrations run on a direct connection before the pool exists, so a
            # failing migration cannot leave half the pool serving an old schema.
            await self.run_migrations()

            self.pool = await asyncpg.create_pool(
                dsn=settings.database_url,
                min_size=2,
                max_size=10,
            )
            logger.info("Orchestration connection pool ready")

    async def disconnect(self):
        if self.pool:
            logger.info("Closing asyncpg connection pool...")
            await self.pool.close()
            self.pool = None

    async def healthy(self) -> bool:
        """Prove the pool can actually round-trip a query.

        `self.pool is not None` is not the same question. A pool object survives
        Postgres going away, and the whole point of surfacing this on /health is
        to catch that case rather than to confirm that connect() was called.
        """
        if not self.pool:
            return False
        try:
            async with self.pool.acquire() as conn:
                return await conn.fetchval("SELECT 1") == 1
        except Exception as exc:
            logger.warning("Database health probe failed", error=str(exc))
            return False

    async def run_migrations(self):
        logger.info("Starting database migrations...")
        conn = await asyncpg.connect(settings.database_url)
        applied = 0
        try:
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS migrations_log (
                    migration_file VARCHAR(255) PRIMARY KEY,
                    executed_at TIMESTAMP DEFAULT NOW(),
                    migration_batch_id VARCHAR(255)
                );
                """
            )
            await conn.execute(
                "ALTER TABLE migrations_log ADD COLUMN IF NOT EXISTS migration_batch_id VARCHAR(255)"
            )

            current_dir = os.path.dirname(os.path.abspath(__file__))
            # migrations lives at app/migrations (sibling of app/core)
            migrations_dir = os.path.join(os.path.dirname(current_dir), "migrations")
            migration_files = sorted(glob.glob(os.path.join(migrations_dir, "*.sql")))

            if not migration_files:
                logger.warning("No migration files found", directory=migrations_dir)
                return

            for file_path in migration_files:
                filename = os.path.basename(file_path)

                already_executed = await conn.fetchval(
                    "SELECT 1 FROM migrations_log WHERE migration_file = $1", filename
                )
                if already_executed:
                    applied += 1
                    logger.debug("Migration already executed, skipping", migration=filename)
                    continue

                logger.info("Executing migration", migration=filename)
                with open(file_path, "r", encoding="utf-8") as f:
                    sql = f.read()

                # An empty (or comment-only) migration file makes asyncpg return
                # None for the statement, and the driver then raises
                # "AttributeError: 'NoneType' object has no attribute 'decode'",
                # aborting startup entirely -- this exact bug crash-looped the
                # Exam service via its empty 005_seed_writing_questions.sql. Skip
                # it WITHOUT recording it as applied, so it still runs once real
                # SQL is added.
                if not sql.strip():
                    logger.warning(
                        "Migration is empty - skipping (not marked as applied)",
                        migration=filename,
                    )
                    continue

                async with conn.transaction():
                    await conn.execute(sql)
                    await conn.execute(
                        "INSERT INTO migrations_log (migration_file, migration_batch_id) VALUES ($1, $2)",
                        filename,
                        os.getenv("MIGRATION_BATCH_ID"),
                    )
                applied += 1
                logger.info("Migration executed successfully", migration=filename)
        finally:
            self.migrations_applied = applied
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
                logger.info("Migration rolled back successfully", migration=filename)
        finally:
            await conn.close()


db = Database()
