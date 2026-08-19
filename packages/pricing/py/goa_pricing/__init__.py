"""Shared LLM price table for GOA's Python services (GOA-135).

One copy, deliberately -- and this package exists because the alternative was
measured rather than imagined. Before it, five call sites priced the same model
five different ways:

    services/gateway/config.go:76        $2.00 / $10.00   then-current
    services/rag/.../rag_service.py:555  $0.25 / $1.25    8x under  (Haiku prices)
    services/writing/app/agents.py:549   $3.00 / $15.00   1.5x over (Sonnet prices)
    services/writing/cv_processor/...    $1.00 / $5.00    2x under
    services/ingestion/handler.py:660    $8.00 / $40.00   4x over   (Opus-4-6 prices)

Every one of them was confidently reporting a number. The Gateway's own comment
(handlers/admin.go:99) had already named the failure mode:

    "Two copies of this arithmetic would drift, and the failure would be silent
     in the worst way: an alert threshold measuring something subtly different
     from the figure an operator sees when they go looking."

It was right, and it had already happened four times behind its back.

WHERE THE PRICES COME FROM
--------------------------
`LLM_PRICING_JSON` -- the same environment variable the Gateway reads
(services/gateway/config.go:76), with the same default. The Gateway keeps its own
Go parser and remains the authority for billing roll-ups; this module is the
Python reader of the same configuration. One variable, one set of numbers, two
readers -- not two tables that happen to agree today.

Prices themselves are manually synchronized from AgentRouter's live catalogue;
the router exposes no pricing API. Parity tests keep every shipped mirror equal,
but provider freshness remains an explicit operational check.

UNPRICED MODELS RETURN None, NEVER 0.0
--------------------------------------
`cost_usd` returns None for a model it cannot price. Returning 0.0 would make
"we do not know what this cost" indistinguishable from "this was free" -- the
BUG-055 shape applied to money, and precisely what let four services drift
unnoticed. Callers must handle None and are expected to record it as an absent
value rather than a zero one.

Distributed the way packages/security/py already is: each service's Dockerfile
copies this directory in, and the build context is the repository root.
"""

from goa_pricing.table import (
    DEFAULT_PRICING_JSON,
    ModelPrice,
    UnpricedModelError,
    cost_usd,
    known_models,
    price_for,
)

__all__ = [
    "DEFAULT_PRICING_JSON",
    "ModelPrice",
    "UnpricedModelError",
    "cost_usd",
    "known_models",
    "price_for",
]
