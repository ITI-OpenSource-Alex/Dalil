"""GOA-030/036 — drive one real protocol-v3 speaking interview through the Gateway.

Not a test. This is the hand-probe that establishes what the v3 socket actually
does end to end -- Gateway JWT check, WebSocket upgrade, proxy relay, bank
selection, examiner TTS, candidate audio, sidecar STT, scoring, persistence --
before any suite is written against it. The repo's standing rule is that a green
suite over a broken system is the default failure mode here, so the flow gets
run and watched first.

It uses the `abandon` path deliberately. A full three-part session is 11-14
minutes by design: the 60-second preparation timer is a scoring rule the server
refuses to skip, and the long turn has a 60-second floor. `abandon` is a
first-class transition that scores what exists and records the rest as absent
(never as zero), so it exercises the whole pipeline inside a bounded window
without a test-only timing override weakening a scoring rule.

Usage:
    python perf/interview_probe.py --token "$(cat /tmp/goa_tok.txt)"
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from websockets.sync.client import connect

FIXTURE = Path(__file__).parent / "fixtures" / "ielts-part2-answer.16k.pcm"
# 16 kHz, 16-bit, mono -- what stt.go declares and the sidecar decodes.
BYTES_PER_SECOND = 16000 * 2
CHUNK_BYTES = 16000  # ~0.5s, roughly what MediaRecorder emits


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--token", required=True)
    parser.add_argument("--gateway", default="ws://localhost:8080")
    parser.add_argument("--user-id", default="probe-user")
    parser.add_argument("--answer-seconds", type=int, default=8)
    parser.add_argument("--turns", type=int, default=2, help="candidate turns before abandon")
    parser.add_argument("--timeout", type=int, default=240)
    args = parser.parse_args()

    clip = FIXTURE.read_bytes()[: args.answer_seconds * BYTES_PER_SECOND]
    url = f"{args.gateway}/api/speaking/ws"

    started = time.time()
    timeline: list[tuple[float, str, str]] = []

    def mark(kind: str, detail: str = "") -> None:
        timeline.append((round(time.time() - started, 2), kind, detail))
        print(f"{timeline[-1][0]:>7.2f}s  {kind:<22} {detail[:90]}")

    with connect(
        url,
        additional_headers={"Cookie": f"access_token={args.token}"},
        max_size=None,
        open_timeout=30,
    ) as socket:
        mark("connected", url)
        socket.send(
            json.dumps(
                {
                    "type": "session_init",
                    "protocolVersion": 3,
                    "userId": args.user_id,
                    # Raw PCM: the one format whose duration follows from its
                    # byte count, and what the fixture actually contains.
                    "audioFormat": "audio/pcm;rate=16000",
                }
            )
        )

        candidate_turns = 0
        sent_ready = False
        deadline = time.time() + args.timeout

        while time.time() < deadline:
            try:
                raw = socket.recv(timeout=max(1, deadline - time.time()))
            except TimeoutError:
                mark("recv_timeout", "no frame before deadline")
                break

            if isinstance(raw, (bytes, bytearray)):
                mark("examiner_audio", f"{len(raw)} bytes")
                continue

            try:
                frame = json.loads(raw)
            except json.JSONDecodeError:
                mark("non_json_text", raw[:80])
                continue

            kind = frame.get("type", "?")
            detail = json.dumps({k: v for k, v in frame.items() if k != "type"})[:110]
            mark(kind, detail)

            if kind == "session_started" and not sent_ready:
                sent_ready = True
                socket.send(json.dumps({"type": "ready"}))

            elif kind == "examiner_turn" and frame.get("expects_response"):
                if candidate_turns >= args.turns:
                    socket.send(json.dumps({"type": "abandon"}))
                    mark("-> abandon", f"after {candidate_turns} candidate turns")
                    continue
                for offset in range(0, len(clip), CHUNK_BYTES):
                    socket.send(clip[offset : offset + CHUNK_BYTES])
                socket.send(json.dumps({"type": "audio_end"}))
                candidate_turns += 1
                mark("-> candidate_audio", f"turn {candidate_turns}, {len(clip)} bytes")

            elif kind in {"evaluation", "session_complete"}:
                mark("terminal", kind)
                break

            elif kind == "error" or kind == "policy_error":
                mark("terminal_error", detail)
                break

    print("\n--- frame summary ---")
    counts: dict[str, int] = {}
    for _, kind, _ in timeline:
        counts[kind] = counts.get(kind, 0) + 1
    for kind, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"  {n:>3}  {kind}")
    print(f"\ntotal {time.time() - started:.1f}s")


if __name__ == "__main__":
    main()
