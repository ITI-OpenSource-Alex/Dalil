import asyncio
import os

from app.core.database import db


async def main() -> None:
    if os.getenv("MIGRATION_DIRECTION") == "down":
        await db.run_down_migrations()
    else:
        await db.connect()
    await db.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
