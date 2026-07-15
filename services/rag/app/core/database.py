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
            self.pool = await asyncpg.create_pool(
                dsn=settings.database_url,
                min_size=2,
                max_size=10,
                init=register_vector
            )
            # Run migrations on connection startup
            await self.run_migrations()

    async def disconnect(self):
        if self.pool:
            logger.info("Closing asyncpg connection pool...")
            await self.pool.close()
            self.pool = None

    async def run_migrations(self):
        logger.info("Starting database migrations...")
        async with self.pool.acquire() as conn:
            # Create migrations_log table if it doesn't exist
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS migrations_log (
                    migration_file VARCHAR(255) PRIMARY KEY,
                    executed_at TIMESTAMP DEFAULT NOW()
                );
            """)

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

                    # Run migration in a transaction block
                    async with conn.transaction():
                        await conn.execute(sql)
                        await conn.execute(
                            "INSERT INTO migrations_log (migration_file) VALUES ($1)", filename
                        )
                    logger.info("Migration %s executed successfully", filename)
                else:
                    logger.debug("Migration %s already executed, skipping", filename)

db = Database()
