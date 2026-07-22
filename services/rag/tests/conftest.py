import os

# Settings is strict — without these the whole suite fails at COLLECTION with a pydantic
# ValidationError, which reads like a code bug rather than a missing local env var.
os.environ.setdefault("DATABASE_URL", "postgresql://goa:goa_pass@localhost:5432/rag_db")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-anthropic-key")
os.environ.setdefault("INTERNAL_API_KEY", "supersecret_internal_key_123")
os.environ.setdefault("EMBEDDING_BASE_URL", "http://localhost:11434/v1")
os.environ.setdefault("EMBEDDING_MODEL", "nomic-embed-text")
os.environ.setdefault("EMBEDDING_API_KEY", "ollama")
import pytest  # noqa: E402


def _aiobotocore_botocore_mismatch() -> str | None:
    """aiobotocore pins a narrow botocore range and reaches into botocore internals.

    In a shared local virtualenv another service's newer boto3 pulls a botocore that
    aiobotocore cannot drive, and every S3-touching test dies with an opaque
    "compute_endpoint_resolver_builtin_defaults() missing 3 required positional
    arguments" TypeError. The RAG container installs a matched pair and is unaffected,
    so this is a local-environment artifact, not a defect in this service.
    """
    try:
        from importlib.metadata import version

        import aiobotocore.args  # noqa: F401
        import inspect

        from botocore.args import ClientArgsCreator

        sig = inspect.signature(ClientArgsCreator.compute_endpoint_resolver_builtin_defaults)
        # aiobotocore 2.12.x calls this with the botocore ~1.34 argument list.
        if len(sig.parameters) > 9:
            return (
                f"aiobotocore {version('aiobotocore')} is incompatible with botocore "
                f"{version('botocore')} in this environment. Run these tests in the "
                f"container instead: docker compose exec rag python -m pytest tests/"
            )
    except Exception:
        return None
    return None


_MISMATCH = _aiobotocore_botocore_mismatch()


@pytest.fixture(autouse=True)
def _skip_on_aws_dependency_mismatch(request):
    """Skip only the S3-touching suites, with an actionable message, instead of letting
    them fail with an unreadable TypeError from inside aiobotocore."""
    if _MISMATCH and "visa_integration" in request.node.nodeid:
        pytest.skip(_MISMATCH)
