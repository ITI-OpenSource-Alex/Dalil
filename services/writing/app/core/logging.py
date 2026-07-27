"""Structured logging with correlation IDs.

Mirrors services/rag/app/core/logging.py and services/exam/app/core/logging.py
deliberately -- three services emitting the same shape is what makes a
correlation ID useful, since tracing a request means grepping one value across
all of them.

The gateway generates an ID, forwards it on every downstream call, and it
arrived here correctly all along. Writing simply had no structured logging at
all, so requests appeared only in uvicorn's access log, which carries no
correlation field (BUG-030).
"""

import logging
import sys
from contextvars import ContextVar

import structlog

correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="")


def inject_correlation_id(logger, method_name, event_dict):
    correlation_id = correlation_id_var.get()
    if correlation_id:
        event_dict["correlation_id"] = correlation_id
    return event_dict


def configure_logging():
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=logging.INFO,
    )
    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="iso"),
            inject_correlation_id,
            structlog.processors.JSONRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
