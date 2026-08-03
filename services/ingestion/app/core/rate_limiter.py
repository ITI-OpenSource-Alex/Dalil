import asyncio
import random


async def polite_delay(min_seconds: float = 1.0, max_seconds: float =2.0):
    """Sleeps for a random duration between min_seconds and max_seconds."""
    delay = random.uniform(min_seconds, max_seconds)
    await asyncio.sleep(delay)