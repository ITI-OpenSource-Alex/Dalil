import asyncio
import httpx
from langchain_anthropic import ChatAnthropic
from pydantic import BaseModel

class IntentResult(BaseModel):
    intent: str
    confidence: float

# Initialize ChatAnthropic
llm = ChatAnthropic(
    model="claude-opus-5",
    anthropic_api_key="sk-dummy",
    anthropic_api_url="https://agentrouter.org"
)

# Monkeypatch the beta tools attribute
class DummyBeta:
    pass

if not hasattr(llm._async_client, "beta"):
    llm._async_client.beta = DummyBeta()
llm._async_client.beta.tools = llm._async_client

# mock the httpx request so we don't actually hit the network and timeout if it's wrong, we just want to see if it calls .messages.create
async def mock_post(*args, **kwargs):
    raise Exception(f"SUCCESS: Hitting {args[0]}")

llm._async_client._client = httpx.AsyncClient()
llm._async_client._client.post = mock_post

structured_llm = llm.with_structured_output(IntentResult)

async def main():
    try:
        await structured_llm.ainvoke([{"role": "user", "content": "I want to practice speaking"}])
    except Exception as e:
        print(str(e))

asyncio.run(main())
