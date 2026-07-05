import asyncio
from langchain_community.chat_message_histories import RedisChatMessageHistory
from langchain.memory import ConversationBufferWindowMemory
from app.core.config import settings


def get_session_memory(session_id: str) -> ConversationBufferWindowMemory:
    """
    Creates and returns a ConversationBufferWindowMemory instance
    wrapped around RedisChatMessageHistory with a 24-hour TTL.
    """

    history = RedisChatMessageHistory(
        session_id=session_id,
        url=settings.redis_url,
        ttl=86400
    )

    # k=10 defines the window size (last 10 turns)

    return ConversationBufferWindowMemory(
        k=10,
        chat_memory=history,
        return_messages=True
    )


async def load_memory_variables(memory: ConversationBufferWindowMemory, inputs: dict) -> dict:
    """
    Loads conversation context from Redis memory asynchronously
    using the running event loop's thread pool executor to prevent event loop blocking.
    """

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None,
        memory.load_memory_variables,
        inputs
    )


async def save_context(memory: ConversationBufferWindowMemory, inputs: dict, outputs: dict) -> None:
    """
    Saves conversation context to Redis memory asynchronously
    using the running event loop's thread pool executor to prevent event loop blocking.
    """

    loop = asyncio.get_running_loop()
    await loop.run_in_executor(
        None,
        memory.save_context,
        inputs,
        outputs
    )