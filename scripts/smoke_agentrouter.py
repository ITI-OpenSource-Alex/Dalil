"""One-call AgentRouter diagnostic with no application services involved.

Loads provider settings from the process environment and, when present, the
repository's .env file. It never prints credentials. The OpenAI-compatible
wire format is intentional: it makes the probe reusable in non-GOA projects.
"""

from __future__ import annotations

import argparse
import json
import os
import queue
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path


DEFAULT_BASE_URL = "https://agentrouter.org"
DEFAULT_MODEL = "claude-opus-5"
DEFAULT_USER_AGENT = (
    "Kilo-Code/7.4.11 ai-sdk/provider-utils/4.0.27 runtime/bun/1.3.14"
)


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        os.environ.setdefault(name.strip(), value.strip().strip('"').strip("'"))


def _endpoint(base_url: str) -> str:
    base = base_url.rstrip("/")
    if base.endswith("/v1"):
        return f"{base}/chat/completions"
    return f"{base}/v1/chat/completions"


def _error_detail(body: bytes) -> str:
    text = body.decode("utf-8", errors="replace")[:500]
    try:
        payload = json.loads(text)
        error = payload.get("error", payload)
        if isinstance(error, dict):
            return str(error.get("message") or error.get("type") or error)[:500]
    except (json.JSONDecodeError, AttributeError):
        pass
    return text


def _call(
    *, token: str, base_url: str, model: str, user_agent: str, timeout: float
) -> tuple[dict, int]:
    body = json.dumps(
        {
            "model": model,
            "messages": [{"role": "user", "content": "Reply with exactly: OK"}],
            "max_tokens": 16,
            "temperature": 0,
            "stream": False,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        _endpoint(base_url),
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": user_agent,
        },
    )

    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
            latency_ms = round((time.perf_counter() - started) * 1000, 1)
            content = payload.get("choices", [{}])[0].get("message", {}).get("content")
            result = {
                "ok": response.status == 200,
                "status": response.status,
                "model": payload.get("model", model),
                "latency_ms": latency_ms,
                "content": str(content)[:80] if content is not None else None,
                "usage": payload.get("usage"),
            }
            return result, 0 if response.status == 200 else 1
    except urllib.error.HTTPError as exc:
        return {
            "ok": False,
            "status": exc.code,
            "latency_ms": round((time.perf_counter() - started) * 1000, 1),
            "error": _error_detail(exc.read()),
        }, 1
    except (TimeoutError, urllib.error.URLError) as exc:
        return {
            "ok": False,
            "latency_ms": round((time.perf_counter() - started) * 1000, 1),
            "error": str(getattr(exc, "reason", exc))[:500],
        }, 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Make one isolated AgentRouter call")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--model", default=None)
    args = parser.parse_args()

    repository_root = Path(__file__).resolve().parents[1]
    _load_dotenv(repository_root / ".env")

    token = os.getenv("ANTHROPIC_AUTH_TOKEN") or os.getenv("ANTHROPIC_API_KEY")
    if not token:
        print(json.dumps({"ok": False, "error": "provider token is not configured"}))
        return 2

    base_url = (
        os.getenv("GOA_LLM_BASE_URL")
        or os.getenv("ANTHROPIC_BASE_URL")
        or DEFAULT_BASE_URL
    )
    model = args.model or os.getenv("LLM_MODEL") or DEFAULT_MODEL
    user_agent = os.getenv("ANTHROPIC_USER_AGENT") or DEFAULT_USER_AGENT

    # urllib's socket timeout is per operation, not a wall-clock budget. A
    # gateway that drips bytes can therefore exceed it indefinitely. The daemon
    # worker gives this smoke test a hard total deadline as well.
    results: queue.Queue[tuple[dict, int]] = queue.Queue(maxsize=1)

    def worker() -> None:
        results.put(
            _call(
                token=token,
                base_url=base_url,
                model=model,
                user_agent=user_agent,
                timeout=args.timeout,
            )
        )

    started = time.perf_counter()
    threading.Thread(target=worker, daemon=True).start()
    try:
        result, exit_code = results.get(timeout=args.timeout)
    except queue.Empty:
        result = {
            "ok": False,
            "latency_ms": round((time.perf_counter() - started) * 1000, 1),
            "error": f"hard timeout after {args.timeout:g}s",
        }
        exit_code = 1

    print(json.dumps(result, ensure_ascii=False))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
