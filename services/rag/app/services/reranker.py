"""
services/rag/app/services/reranker.py

Cross-Encoder Re-Ranker component.
Attempts to load sentence-transformers (ms-marco-MiniLM-L-6-v2) if supported by the OS environment.
Degrades gracefully to Token-Overlap / BM25 fallback re-ranking if PyTorch/musl is incompatible,
ensuring candidates are re-ordered and the pipeline never fails.
"""

import logging
import re
import ctypes
from typing import List, Dict, Any

logger = logging.getLogger("rag_service.reranker")

_reranker_instance = None


def init_reranker():
    global _reranker_instance
    if _reranker_instance is None:
        try:
            # Preload glibc compatibility stub if running in Alpine musl environment
            try:
                ctypes.CDLL("/usr/lib/libfix.so", mode=ctypes.RTLD_GLOBAL)
            except Exception:
                pass

            logger.info("Loading CrossEncoder model 'cross-encoder/ms-marco-MiniLM-L-6-v2'...")
            from sentence_transformers import CrossEncoder
            _reranker_instance = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
            logger.info("CrossEncoder model loaded successfully.")
        except Exception as exc:
            # ERROR, not warning. This is the difference between "re-ranking is on"
            # and "a token-overlap heuristic is wearing re-ranking's name". A
            # benchmark captured in this state reports rerank_enabled=true while
            # measuring something that is not the cross-encoder.
            logger.error(
                "CROSS-ENCODER UNAVAILABLE -- serving DEGRADED token-overlap fallback. "
                "Benchmarks captured now do NOT measure the cross-encoder. Cause: %s",
                exc,
            )
            _reranker_instance = "fallback"

    try:
        from app.core.metrics import RERANK_MODE

        RERANK_MODE.set(0 if _reranker_instance == "fallback" else 1)
    except Exception:  # metrics must never gate startup
        pass


def get_reranker():
    return _reranker_instance


def is_degraded() -> bool:
    """True when the cross-encoder failed to load and the fallback is serving.

    Exposed so callers -- the query path, the benchmark harness, the health check --
    can report the mode that is actually running rather than the one configured.
    """
    return _reranker_instance is None or _reranker_instance == "fallback"


def _count_fallback(cause: str) -> None:
    """Record that a rank() call was served by the degraded path."""
    try:
        from app.core.metrics import RERANK_FALLBACK_TOTAL

        RERANK_FALLBACK_TOTAL.labels(cause=cause).inc()
    except Exception:  # telemetry must never break retrieval
        pass


def _tokenize(text: str) -> List[str]:
    return [w.lower() for w in re.findall(r'\w+', text)]


def _fallback_token_overlap_score(query: str, content: str) -> float:
    """Calculate token overlap / BM25 relevance score for query against chunk content."""
    q_tokens = _tokenize(query)
    c_tokens = _tokenize(content)

    if not q_tokens or not c_tokens:
        return 0.0

    c_freq = {}
    for t in c_tokens:
        c_freq[t] = c_freq.get(t, 0) + 1

    score = 0.0
    for q in q_tokens:
        if q in c_freq:
            tf = c_freq[q]
            score += (tf * 1.5) / (tf + 0.5 + 1.5 * (len(c_tokens) / 100.0))

    return score


class Reranker:
    def __init__(self):
        self.model = get_reranker()

    def rank(self, query: str, candidates: List[Dict[str, Any]], top_n: int = 5) -> List[Dict[str, Any]]:
        if not candidates:
            return []

        # Case 1: Real CrossEncoder model loaded
        if self.model is not None and self.model != "fallback":
            try:
                pairs = [(query, c["content"]) for c in candidates]
                scores = self.model.predict(pairs)

                for idx, candidate in enumerate(candidates):
                    candidate["rerank_score"] = float(scores[idx])

                sorted_candidates = sorted(candidates, key=lambda x: x["rerank_score"], reverse=True)
                return sorted_candidates[:top_n]
            except Exception as exc:
                logger.warning("CrossEncoder prediction failed, falling back to token overlap: %s", exc)
                _count_fallback("predict_failed")
        else:
            _count_fallback("model_unavailable")

        # Case 2: Fallback Token Overlap / BM25 re-ranking
        for candidate in candidates:
            overlap_score = _fallback_token_overlap_score(query, candidate["content"])
            init_sim = candidate.get("similarity", 0.5)
            candidate["rerank_score"] = init_sim + (0.5 * overlap_score)

        sorted_candidates = sorted(candidates, key=lambda x: x["rerank_score"], reverse=True)
        return sorted_candidates[:top_n]