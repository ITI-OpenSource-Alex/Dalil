import asyncio

from app.core.database import db


async def main() -> None:
    await db.connect()
    await db.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
