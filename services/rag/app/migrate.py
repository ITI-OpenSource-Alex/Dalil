import asyncio

from app.core.database import db


async def main() -> None:
    await db.run_migrations()


if __name__ == "__main__":
    asyncio.run(main())
