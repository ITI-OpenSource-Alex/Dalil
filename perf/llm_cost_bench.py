"""GOA-135 benchmark harness — LLM cost accounting, client lifecycle, retry policy.

One harness, run twice (--phase pre, --phase post). A metric computed by two
different code paths is not a comparison, so both runs go through here.

The cost metrics (C1, C1b) are deliberately measured WITHOUT the provider: they
are pure arithmetic over known token counts, so the answer is exact rather than
sampled, and the run is reproducible on any machine. The connection, latency and
retry metrics (C3-C7) need a real endpoint and are skipped with an explicit
reason when one is not configured -- never silently.

Usage:
    python perf/llm_cost_bench.py --phase pre  --out perf/reports/
    python perf/llm_cost_bench.py --phase post --out perf/reports/
"""

import argparse
import json
import os
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# The shared packages, on sys.path before anything else runs. Without this the
# C1 mirrors below silently take their pre-fix branch and the post run reports
# the defect as unfixed -- which is exactly what happened on the first attempt.
for _extra in ("packages/pricing/py", "packages/security/py", "packages/contracts/py"):
    _candidate = str(REPO_ROOT / _extra)
    if _candidate not in sys.path:
        sys.path.insert(0, _candidate)

# The live AgentRouter prices, independently captured from its catalogue. This
# must not import the shipped table: a wrong shared table must produce a ratio
# other than 1.000 instead of certifying itself.
# Hardcoded HERE on purpose: this is the benchmark's independent yardstick. If it
# imported the same module the services use, a wrong shared table would produce a
# ratio of 1.000 and the harness would certify its own bug.
TRUE_PRICES = {
    "claude-opus-4-8": (6.00, 30.00),
    "claude-opus-5": (2.00, 10.00),
    "gpt-5.6-sol": (6.00, 36.00),
}

# A representative RAG query shape, from the migration plan's budget model:
# 2,000 prompt / 300 completion.
SAMPLE_INPUT_TOKENS = 2000
SAMPLE_OUTPUT_TOKENS = 300

MODEL = os.environ.get("LLM_MODEL", "claude-opus-5")


def true_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    prompt_per_1m, completion_per_1m = TRUE_PRICES[model]
    return (input_tokens * prompt_per_1m + output_tokens * completion_per_1m) / 1_000_000


# --------------------------------------------------------------------------
# C1 -- per-service cost arithmetic
# --------------------------------------------------------------------------

def _rag_cost(input_tokens: int, output_tokens: int) -> float:
    """Mirror of services/rag/app/services/rag_service.py cost arithmetic.

    Mirrored rather than imported because importing rag_service pulls asyncpg,
    langchain, langfuse and a live settings object -- a benchmark that cannot run
    without the whole service is a benchmark nobody runs. The DoD requires the
    post-run to confirm this mirror still matches the source.
    """
    try:
        from goa_pricing import cost_usd  # noqa: F401  (present only post-fix)
    except ImportError:
        return (input_tokens * 0.25 + output_tokens * 1.25) / 1_000_000
    from goa_pricing import cost_usd
    return cost_usd(MODEL, input_tokens, output_tokens)


def _writing_cost(input_tokens: int, output_tokens: int) -> float:
    """Mirror of services/writing/app/agents.py:549."""
    try:
        from goa_pricing import cost_usd
    except ImportError:
        return (input_tokens * 3 + output_tokens * 15) / 1_000_000
    return cost_usd(MODEL, input_tokens, output_tokens)


def _cv_processor_cost(input_tokens: int, output_tokens: int) -> float:
    """Mirror of services/writing/cv_processor/structured.py:11-12,124-127."""
    try:
        from goa_pricing import cost_usd
    except ImportError:
        return (input_tokens * 1.0 + output_tokens * 5.0) / 1_000_000
    return cost_usd(MODEL, input_tokens, output_tokens)


def _ingestion_cost(input_tokens: int, output_tokens: int) -> float:
    """Mirror of services/ingestion/handler.py:660-661,682-685."""
    try:
        from goa_pricing import cost_usd
    except ImportError:
        input_cost = float(os.getenv("EXTRACTION_INPUT_COST_PER_1M", "8"))
        output_cost = float(os.getenv("EXTRACTION_OUTPUT_COST_PER_1M", "40"))
        return (input_tokens * input_cost + output_tokens * output_cost) / 1_000_000
    return cost_usd(MODEL, input_tokens, output_tokens)


COST_SITES = {
    "rag": (_rag_cost, "services/rag/app/services/rag_service.py:555"),
    "writing": (_writing_cost, "services/writing/app/agents.py:549"),
    "cv_processor": (_cv_processor_cost, "services/writing/cv_processor/structured.py:124"),
    "ingestion": (_ingestion_cost, "services/ingestion/handler.py:682"),
}


# Where each site's cost arithmetic actually lives, so the mirrors above can be
# checked against the real source rather than trusted. A mirror that has drifted
# from the code it mirrors would report a clean 1.000 for a service still doing
# the wrong thing -- the benchmark would certify the bug.
COST_SOURCE_FILES = {
    "rag": "services/rag/app/services/rag_service.py",
    "writing": "services/writing/app/agents.py",
    "cv_processor": "services/writing/cv_processor/structured.py",
    "ingestion": "services/ingestion/handler.py",
}

# Literal price pairs each site once shipped. Finding any of these still in the
# source means the site was not actually migrated, whatever the mirror says.
KNOWN_BAD_LITERALS = {
    "rag": ("0.25", "1.25"),
    "writing": ("* 3 ", "* 15 "),
    "cv_processor": ("INPUT_COST_PER_MILLION_USD", "OUTPUT_COST_PER_MILLION_USD"),
    "ingestion": ("EXTRACTION_INPUT_COST_PER_1M", "EXTRACTION_OUTPUT_COST_PER_1M"),
}


def _source_uses_shared_table(name: str) -> dict:
    """Confirm the real file delegates to goa_pricing and carries no old literal."""
    path = REPO_ROOT / COST_SOURCE_FILES[name]
    if not path.exists():
        return {"checked": False, "reason": f"{path} not found"}
    source = path.read_text(encoding="utf-8")

    # Comments explaining the migration necessarily quote the old constants, so
    # strip them before looking for leftovers.
    code_only = "\n".join(
        line.split("#", 1)[0] for line in source.splitlines()
    )

    return {
        "checked": True,
        "imports_goa_pricing": "goa_pricing" in code_only,
        "old_literals_present": [
            lit for lit in KNOWN_BAD_LITERALS[name] if lit in code_only
        ],
    }


def measure_cost_ratios() -> dict:
    truth = true_cost(MODEL, SAMPLE_INPUT_TOKENS, SAMPLE_OUTPUT_TOKENS)
    out = {
        "model": MODEL,
        "input_tokens": SAMPLE_INPUT_TOKENS,
        "output_tokens": SAMPLE_OUTPUT_TOKENS,
        "true_cost_usd": round(truth, 8),
        "sites": {},
    }
    for name, (fn, where) in COST_SITES.items():
        reported = fn(SAMPLE_INPUT_TOKENS, SAMPLE_OUTPUT_TOKENS)
        entry = {
            "source": where,
            "reported_cost_usd": round(reported, 8),
            "cost_ratio": round(reported / truth, 6) if truth else None,
        }
        entry.update(_source_uses_shared_table(name))
        out["sites"][name] = entry
    return out


# --------------------------------------------------------------------------
# C1b -- the Gateway's canonical path, read from its own default price table
# --------------------------------------------------------------------------

def measure_gateway_ratio() -> dict:
    """Parse gateway/config.go's LLMPricingJSON default and check it against truth.

    Static parse rather than a live /admin/costs call: the value under test is the
    price table, and reading it from source proves the default is right regardless
    of whether a Gateway happens to be running.
    """
    cfg = (REPO_ROOT / "services" / "gateway" / "config.go").read_text(encoding="utf-8")
    marker = 'LLMPricingJSON'
    line = next((ln for ln in cfg.splitlines() if marker in ln), None)
    if line is None:
        return {"available": False, "reason": "LLMPricingJSON not found in gateway/config.go"}

    start = line.find('default:"')
    if start == -1:
        return {"available": False, "reason": "no default tag on LLMPricingJSON"}
    raw = line[start + len('default:"'):].rstrip()
    raw = raw[: raw.rfind('"')].replace('\\"', '"')

    try:
        table = json.loads(raw)
    except ValueError as exc:
        return {"available": False, "reason": f"unparseable default: {exc}"}

    entry = table.get(MODEL)
    if entry is None:
        return {"available": False, "reason": f"{MODEL} absent from gateway price table"}

    reported = (
        SAMPLE_INPUT_TOKENS * entry["prompt_per_1m"]
        + SAMPLE_OUTPUT_TOKENS * entry["completion_per_1m"]
    ) / 1_000_000
    truth = true_cost(MODEL, SAMPLE_INPUT_TOKENS, SAMPLE_OUTPUT_TOKENS)
    return {
        "available": True,
        "source": "services/gateway/config.go LLMPricingJSON default",
        "models_priced": sorted(table),
        "reported_cost_usd": round(reported, 8),
        "cost_ratio": round(reported / truth, 6),
    }


# --------------------------------------------------------------------------
# C3/C5/C7 -- client lifecycle and retry, against a real endpoint
# --------------------------------------------------------------------------

def measure_client_behaviour(calls: int) -> dict:
    """A/B the two client lifecycles over N sequential LLM calls each.

    `unpooled` builds a fresh AsyncAnthropic per call, each with its own default
    httpx client -- what rag_service.py:85 does today. `pooled` builds one and
    reuses it -- the fix. Both arms hit the same endpoint with the same tiny
    payload back to back, so the difference between them is connection setup.

    Connection count is reported as `tcp_connects`, measured by counting calls to
    the transport's connect path. An earlier version of this harness counted
    *requests* through a shared transport and reported the result as connections;
    that number was always equal to `calls` no matter which arm ran, because the
    shared transport pooled underneath both. Latency is the honest signal here and
    `tcp_connects` is the corroboration, not the other way round.
    """
    token = os.environ.get("ANTHROPIC_AUTH_TOKEN") or os.environ.get("ANTHROPIC_API_KEY")
    base_url = os.environ.get("ANTHROPIC_BASE_URL")
    if not token or not base_url:
        return {
            "available": False,
            "reason": "ANTHROPIC_AUTH_TOKEN/ANTHROPIC_BASE_URL not set; "
                      "connection, latency and retry metrics require a real endpoint",
        }

    try:
        import httpx
        from anthropic import AsyncAnthropic
    except ImportError as exc:
        return {"available": False, "reason": f"missing dependency: {exc}"}

    import asyncio
    import httpcore

    # httpcore 1.x exposes `create_connection(origin)`; it is called once per new
    # pooled connection, which is exactly the TLS handshake this ticket removes.
    connects = {"n": 0}
    _orig_connect = httpcore.AsyncConnectionPool.create_connection

    def counting_connect(self, origin):
        connects["n"] += 1
        return _orig_connect(self, origin)

    def summarise(latencies):
        lat = sorted(latencies)
        return {
            "min": round(lat[0], 1),
            "p50": round(lat[len(lat) // 2], 1),
            "p95": round(lat[max(0, int(len(lat) * 0.95) - 1)], 1),
            "max": round(lat[-1], 1),
        }

    async def one_arm(pooled: bool) -> dict:
        connects["n"] = 0
        latencies = []
        shared = None
        clients = []

        if pooled:
            shared = AsyncAnthropic(auth_token=token, base_url=base_url, timeout=25.0)
            clients.append(shared)

        for _ in range(calls):
            if pooled:
                client = shared
            else:
                # Exactly rag_service.py:85 -- a fresh client, its own default
                # httpx client, never closed.
                client = AsyncAnthropic(auth_token=token, base_url=base_url, timeout=25.0)
                clients.append(client)
            started = time.perf_counter()
            try:
                await client.messages.create(
                    model=MODEL,
                    max_tokens=8,
                    messages=[{"role": "user", "content": "Reply with exactly: OK"}],
                )
            except Exception:  # noqa: BLE001 -- a failed call still times
                pass
            latencies.append((time.perf_counter() - started) * 1000)

        for c in clients:
            try:
                await c.close()
            except Exception:  # noqa: BLE001
                pass

        return {"latency_ms": summarise(latencies), "tcp_connects": connects["n"]}

    async def run() -> dict:
        httpcore.AsyncConnectionPool.create_connection = counting_connect
        try:
            unpooled = await one_arm(pooled=False)
            pooled = await one_arm(pooled=True)
        finally:
            httpcore.AsyncConnectionPool.create_connection = _orig_connect
        return {"unpooled": unpooled, "pooled": pooled}

    arms = asyncio.run(run())
    return {
        "available": True,
        "calls_per_arm": calls,
        "unpooled": arms["unpooled"],
        "pooled": arms["pooled"],
        "p50_delta_ms": round(
            arms["unpooled"]["latency_ms"]["p50"] - arms["pooled"]["latency_ms"]["p50"], 1
        ),
    }


def measure_auth_failure_requests() -> dict:
    """C7 -- how many outbound requests a permanent 401 costs."""
    base_url = os.environ.get("ANTHROPIC_BASE_URL")
    if not base_url:
        return {"available": False, "reason": "ANTHROPIC_BASE_URL not set"}
    try:
        import httpx
        from anthropic import AsyncAnthropic
    except ImportError as exc:
        return {"available": False, "reason": f"missing dependency: {exc}"}

    import asyncio

    counter = {"n": 0}

    class CountingTransport(httpx.AsyncHTTPTransport):
        async def handle_async_request(self, request):
            counter["n"] += 1
            return await super().handle_async_request(request)

    # Drive the SHIPPED retry loop when the RAG service is importable, so this
    # measures the policy that actually runs rather than a lookalike written
    # here. Falls back to an inline loop -- the pre-fix shape -- and reports
    # which driver it used, because a benchmark that silently measures a
    # different code path is worse than one that skips.
    _import_error = {"reason": None}
    rag_service = None
    for extra in ("services/rag", "packages/pricing/py", "packages/security/py"):
        candidate = str(REPO_ROOT / extra)
        if candidate not in sys.path:
            sys.path.insert(0, candidate)
    # RAG's Settings is strict and would fail construction on a missing
    # DATABASE_URL. Nothing here connects to a database -- only the settings
    # object is built -- so a placeholder is enough. Same treatment as
    # services/rag/tests/conftest.py.
    os.environ.setdefault("DATABASE_URL", "postgresql://unused:unused@127.0.0.1:5432/unused")
    try:
        from app.services import rag_service as _rag  # type: ignore
        rag_service = _rag
    except Exception as exc:  # noqa: BLE001 -- optional; reported in `driver`
        rag_service = None
        _import_error["reason"] = f"{type(exc).__name__}: {exc}"

    async def run():
        http_client = httpx.AsyncClient(transport=CountingTransport())
        client = AsyncAnthropic(
            auth_token="deliberately-invalid-token",
            base_url=base_url,
            http_client=http_client,
            timeout=25.0,
        )
        started = time.perf_counter()
        err = None

        if rag_service is not None:
            rag_service._llm_client = client
            try:
                await rag_service._invoke_llm_with_retry("x")
            except Exception as exc:  # noqa: BLE001
                err = exc
            finally:
                rag_service._llm_client = None
        else:
            for _ in range(2):
                try:
                    await client.messages.create(
                        model=MODEL, max_tokens=8,
                        messages=[{"role": "user", "content": "x"}],
                    )
                    break
                except Exception as exc:  # noqa: BLE001
                    err = exc

        elapsed = (time.perf_counter() - started) * 1000
        await http_client.aclose()
        return counter["n"], elapsed, type(err).__name__ if err else None

    requests, elapsed_ms, err_type = asyncio.run(run())
    return {
        "available": True,
        "driver": (
            "rag_service._invoke_llm_with_retry" if rag_service
            else "inline 2-attempt loop (pre-fix shape)"
        ),
        "driver_fallback_reason": _import_error["reason"],
        "http_requests": requests,
        "wall_ms": round(elapsed_ms, 1),
        "error_type": err_type,
    }


# --------------------------------------------------------------------------

def git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=REPO_ROOT, text=True
        ).strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=["pre", "post"], required=True)
    parser.add_argument("--out", default=str(REPO_ROOT / "perf" / "reports"))
    parser.add_argument("--calls", type=int, default=20,
                        help="sequential LLM calls for the connection/latency metrics")
    parser.add_argument("--skip-provider", action="store_true",
                        help="cost arithmetic only; skips every metric needing a real endpoint")
    args = parser.parse_args()

    cost = measure_cost_ratios()
    gateway = measure_gateway_ratio()

    if args.skip_provider:
        client = {"available": False, "reason": "--skip-provider"}
        auth = {"available": False, "reason": "--skip-provider"}
    else:
        client = measure_client_behaviour(args.calls)
        auth = measure_auth_failure_requests()

    report = {
        "ticket": "GOA-135",
        "phase": args.phase,
        "captured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "git_sha": git_sha(),
        "host": {"platform": platform.platform(), "python": sys.version.split()[0]},
        "providers": {
            "llm": {
                "base_url": os.environ.get("ANTHROPIC_BASE_URL", "<unset>"),
                "model": MODEL,
                "real": bool(client.get("available")),
            }
        },
        "metrics": {
            "C1_cost_ratios": cost,
            "C1b_gateway_cost_ratio": gateway,
            "C3_C4_client_behaviour": client,
            "C7_auth_failure": auth,
        },
    }

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = out_dir / f"GOA-135-{args.phase}-{stamp}.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"wrote {path}")
    print(f"\nC1 -- cost ratio per site (1.000 == correct), model={MODEL}:")
    for name, site in cost["sites"].items():
        print(f"  {name:<14} {site['cost_ratio']:>8.3f}   {site['source']}")
    if gateway.get("available"):
        print(f"  {'gateway':<14} {gateway['cost_ratio']:>8.3f}   {gateway['source']}")
    else:
        print(f"  gateway: unavailable -- {gateway['reason']}")
    if not client.get("available"):
        print(f"\nC3/C4 skipped: {client['reason']}")
    if not auth.get("available"):
        print(f"C7 skipped: {auth['reason']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
