import asyncio
import json
import os
from typing import Optional, Dict, Any

class SpeakingWsClient:
    """Client for replaying transcripts against the Speaking Service 4-agent WebSocket swarm."""
    
    def __init__(self, ws_url: Optional[str] = None):
        self.ws_url = ws_url or os.environ.get("SPEAKING_WS_URL", "ws://localhost:8002/ws/exam")

    async def evaluate_transcript(self, transcript: str, timeout: float = 30.0) -> Dict[str, Any]:
        """Replay transcript as text and wait for the final evaluation event."""
        try:
            import websockets
            async with websockets.connect(self.ws_url, open_timeout=5.0) as ws:
                # Send text transcript payload
                await ws.send(json.dumps({"type": "transcript_replay", "text": transcript}))
                
                # Listen for evaluation event
                start_time = asyncio.get_event_loop().time()
                while asyncio.get_event_loop().time() - start_time < timeout:
                    msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
                    data = json.loads(msg)
                    if data.get("type") == "evaluation":
                        return {
                            "overall_band": float(data.get("overall_band", 0.0)),
                            "criteria": data.get("criteria", {}),
                            "justification": data.get("justification", ""),
                        }
            return {"overall_band": 0.0, "error": "No evaluation event received from WS swarm"}
        except Exception as e:
            return {"overall_band": 0.0, "error": f"WebSocket swarm unavailable: {e}"}

def replay_transcript_sync(transcript: str, ws_url: Optional[str] = None) -> Dict[str, Any]:
    client = SpeakingWsClient(ws_url=ws_url)
    try:
        return asyncio.run(client.evaluate_transcript(transcript))
    except Exception as e:
        return {"overall_band": 0.0, "error": str(e)}
