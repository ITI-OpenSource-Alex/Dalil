import hashlib
import uuid

import pytest

from app.adapters.visa_adapter import VisaSource, VisaSourceAdapter, normalize_text_for_hash
from app.core.crawl_state import CrawlStateManager


def _source(content_hash=None):
    return VisaSource(
        id=uuid.uuid4(),
        country="Germany",
        visa_type="Student",
        issuing_body="Embassy",
        source_url="https://example.test/visa",
        content_hash=content_hash,
    )


@pytest.mark.asyncio
async def test_changed_dry_run_never_calls_llm_or_touch(mocker):
    adapter = VisaSourceAdapter(
        dry_run=True,
        crawl_state_manager=CrawlStateManager(read_only=True),
    )
    mocker.patch.object(adapter, "_fetch_text", return_value="changed text")
    llm = mocker.patch.object(adapter, "_call_llm")
    touch = mocker.patch("app.adapters.visa_adapter.touch_visa_requirement")

    assert await adapter.run([_source("old-hash")]) == []
    llm.assert_not_called()
    touch.assert_not_called()
    assert adapter.last_run_telemetry["remaining"] == 1


@pytest.mark.asyncio
async def test_unchanged_dry_run_never_calls_llm_or_touch(mocker):
    text = "unchanged text"
    content_hash = hashlib.sha256(
        normalize_text_for_hash(text).encode("utf-8")
    ).hexdigest()
    adapter = VisaSourceAdapter(
        dry_run=True,
        crawl_state_manager=CrawlStateManager(read_only=True),
    )
    mocker.patch.object(adapter, "_fetch_text", return_value=text)
    llm = mocker.patch.object(adapter, "_call_llm")
    touch = mocker.patch("app.adapters.visa_adapter.touch_visa_requirement")

    assert await adapter.run([_source(content_hash)]) == []
    llm.assert_not_called()
    touch.assert_not_called()
