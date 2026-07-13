import asyncio
import structlog
import sys
import os


sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


from app.core.database import db
from app.clients.user_client import get_all_users
from app.services.profile_repo import upsert_local_profiles

logger = structlog.get_logger("rag_service.backfill")


async def run_backfill():
    logger.info("Starting local profile backfill...")
    await db.connect()

    total_processed = 0
    total_failed = 0

    try:
        # get_all_users yields batches of 50
        async for user_batch in get_all_users():
            for user in user_batch:
                try:
                    # Treat backfills as the most recent possible truth
                    from datetime import datetime, timezone
                    user['last_synced_at'] = datetime.now(timezone.utc).isoformat()
                    
                    # Funneling through the exact same mapping logic as the SQS consumer!
                    await upsert_local_profiles(user)
                    total_processed += 1
                except Exception as e:
                    total_failed += 1
                    # Failure Isolation: Log and continue
                    logger.error(
                        "Failed to backfill user",
                        user_id=user.get("userId"),
                        error=str(e),
                    )

        logger.info(
            "Backfill completed",
            total_processed=total_processed,
            total_failed=total_failed,
        )

    except Exception as e:
        logger.error("Backfill aborted due to fatal error", error=str(e))
    finally:
        await db.disconnect()


if __name__ == "__main__":
    asyncio.run(run_backfill())
