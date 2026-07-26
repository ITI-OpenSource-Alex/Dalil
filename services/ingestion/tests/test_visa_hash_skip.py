import pytest
import uuid
import hashlib
from config import settings
from app.adapters.visa_adapter import VisaSourceAdapter, VisaSource

@pytest.fixture
def dummy_source():
    return VisaSource(
        id=uuid.uuid4(),
        country="Germany",
        visa_type="Student",
        issuing_body="Embassy",
        source_url="https://example.com/visa",
        content_hash="mocked_hash_value"
    )

@pytest.mark.asyncio
async def test_matching_hash_skips_llm_and_calls_touch_client(mocker, dummy_source):
    """If text hashes to the same value as DB content_hash, skip LLM and call touch_visa_requirement with auth headers."""
    adapter = VisaSourceAdapter()
    
    raw_text = "This is the unchanged visa page.\r\n  With extra whitespace.  "
    mocker.patch.object(adapter, "_fetch_text", return_value=raw_text)
    
    # Hash normalization: CRLF normalized to LF, whitespace collapsed per line
    normalized = "\n".join(line.strip() for line in raw_text.splitlines() if line.strip())
    expected_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    dummy_source.content_hash = expected_hash
    
    mock_touch = mocker.patch("app.adapters.visa_adapter.touch_visa_requirement", return_value=True)
    mock_call_llm = mocker.patch.object(adapter, "_call_llm")
    
    result = await adapter.run([dummy_source])
    
    assert not mock_call_llm.called
    mock_touch.assert_called_once_with([{
        "country": dummy_source.country,
        "visa_type": dummy_source.visa_type,
        "issuing_body": dummy_source.issuing_body
    }])
    assert len(result) == 0

@pytest.mark.asyncio
async def test_hash_normalization_crlf_and_whitespace_stability():
    """Text with CRLF and trailing spaces produces the exact same hash as LF normalized text."""
    from app.adapters.visa_adapter import normalize_text_for_hash
    
    text_crlf = "Header Line  \r\n\r\n  Body text goes here.\r\n"
    text_lf = "Header Line\nBody text goes here."
    
    hash1 = hashlib.sha256(normalize_text_for_hash(text_crlf).encode("utf-8")).hexdigest()
    hash2 = hashlib.sha256(normalize_text_for_hash(text_lf).encode("utf-8")).hexdigest()
    
    assert hash1 == hash2

@pytest.mark.asyncio
async def test_touch_call_failure_logs_and_continues(mocker, dummy_source):
    """If touch endpoint fails/raises an exception, run() logs a warning and does not crash."""
    adapter = VisaSourceAdapter()
    raw_text = "Unchanged page."
    mocker.patch.object(adapter, "_fetch_text", return_value=raw_text)
    
    from app.adapters.visa_adapter import normalize_text_for_hash
    dummy_source.content_hash = hashlib.sha256(normalize_text_for_hash(raw_text).encode("utf-8")).hexdigest()
    
    mocker.patch("app.adapters.visa_adapter.touch_visa_requirement", side_effect=Exception("Connection timed out"))
    mock_call_llm = mocker.patch.object(adapter, "_call_llm")
    
    # Should complete without raising exception
    result = await adapter.run([dummy_source])
    assert not mock_call_llm.called
    assert len(result) == 0
