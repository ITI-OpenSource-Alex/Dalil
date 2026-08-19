import asyncio
import json
import os
from typing import Optional, Dict, Any

class SpeakingWsClient:
    """Experimental transcript client; production evaluation requires PCM audio."""
    
    def __init__(self, ws_url: Optional[str] = None):
        self.ws_url = ws_url or os.environ.get(
            "SPEAKING_WS_URL", "ws://localhost:8080/api/speaking/ws"
        )

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
                        overall_band = data.get("overall_band")
                        if overall_band is None:
                            return {
                                "overall_band": None,
                                "error": "Evaluation event carried no overall_band",
                            }
                        return {
                            "overall_band": float(overall_band),
                            "criteria": data.get("criteria", {}),
                            "justification": data.get("justification", ""),
                        }
            return {
                "overall_band": None,
                "error": "No evaluation event received from WS swarm",
            }
        except Exception as e:
            return {
                "overall_band": None,
                "error": f"WebSocket swarm unavailable: {e}",
            }

def replay_transcript_sync(transcript: str, ws_url: Optional[str] = None) -> Dict[str, Any]:
    client = SpeakingWsClient(ws_url=ws_url)
    try:
        return asyncio.run(client.evaluate_transcript(transcript))
    except Exception as e:
        return {"overall_band": None, "error": str(e)}
