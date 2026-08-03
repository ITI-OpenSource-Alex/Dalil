import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pytest
import asyncio
from evals.ws_client import SpeakingWsClient

@pytest.mark.asyncio
async def test_ws_client_replays_transcript_and_captures_evaluation():
    client = SpeakingWsClient(ws_url="ws://mock-server:8002/ws/exam")
    
    mock_ws = MagicMock()
    mock_ws.send = AsyncMock()
    mock_ws.recv = AsyncMock(return_value='{"type": "evaluation", "overall_band": 7.0, "criteria": {"fluency": 7.0}, "justification": "Good fluency"}')
    
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_ws)
    mock_cm.__aexit__ = AsyncMock(return_value=None)

    with patch("websockets.connect", return_value=mock_cm):
        res = await client.evaluate_transcript("Sample transcript text")
        assert res["overall_band"] == 7.0
        assert res["criteria"]["fluency"] == 7.0
        assert res["justification"] == "Good fluency"

@pytest.mark.asyncio
async def test_ws_client_handles_connection_failure():
    client = SpeakingWsClient(ws_url="ws://invalid-server:8002/ws/exam")
    with patch("websockets.connect", side_effect=OSError("Connection refused")):
        res = await client.evaluate_transcript("Sample transcript text")
        assert res["overall_band"] == 0.0
        assert "WebSocket swarm unavailable" in res["error"]

def test_speaking_absent_is_reported_not_zero():
    from evals.runner import run_speaking_eval
    res = run_speaking_eval({})
    assert res["speaking_accuracy"] is None
