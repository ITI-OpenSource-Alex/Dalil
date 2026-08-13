# GOA-137 — hybrid retrieval delta

## Verdict

The implementation is complete and the benchmark is valid, but the quality and
lexical-utility targets were not met. Hybrid retrieval therefore ships behind
`rag_hybrid_enabled` with the default **off**.

No target or threshold was changed after measurement.

## Comparable evidence

- PRE: `GOA-137-pre-20260808T001139Z.json`
- POST: `GOA-137-post-20260808T002359Z.json`
- Harness SHA-256 on both runs:
  `fcc85a349d1791d66c3e9651079cfa528abec07f43e9cde23ba5c9d458006dbe`
- Frozen corpus on both runs: 2,905 documents, content SHA-256
  `1e3dd24cd7f2f789056f39b5f72b00d042eafd861006c036df9b2a3c286c2b14`
- Dataset: 45 queries: 30 answerable, 15 unanswerable, including 10 manually
  labelled `entity` and 10 manually labelled `numeric` queries.
- Both runs used retrieval-only requests (retrieval plus the real cross-encoder,
  no answer-generation LLM) and reported `rerank_degraded: false`.

The acceptance comparison is PRE `full` (dense, width 15, probes 10, rerank and
threshold enabled) against POST `hybrid` with the same non-hybrid settings.

## Acceptance results

| Metric | PRE full | POST hybrid | Required | Result |
|---|---:|---:|---:|---|
| Recall@5, all | 0.8000 | 0.7667 | ≥ 0.8000 | **MISS** (-0.0333) |
| Recall@10, all | 0.8000 | 0.7667 | ≥ 0.8500 | **MISS** |
| Recall@10, entity | 1.0000 | 0.8000 | ≥ 1.1500 | **MISS** (-2/10 items; target was already above the mathematical ceiling) |
| Recall@10, numeric | 1.0000 | 1.0000 | ≥ 1.1000 | **MISS** (unchanged; target was already above the mathematical ceiling) |
| MRR, entity | 1.0000 | 0.8000 | ≥ 1.1000 | **MISS** |
| nDCG@10, all | 0.7673 | 0.7149 | ≥ 0.7673 | **MISS** |
| Unanswerable refusal rate | 0.1333 | 0.1333 | no regression | PASS |
| False refusal rate | 0.0333 | 0.0333 | no increase | PASS |
| Retrieval p95 | 2406.8 ms | 2228.1 ms | ≤ 3008.5 ms | PASS |
| Reranker degraded | false | false | false both runs | PASS |
| Lexical contribution to entity top-k | n/a | 0.0300 | ≥ 0.2000 | **MISS** |

The category-filtered hybrid arm produced the same aggregate quality and arm-hit
figures as unfiltered hybrid on this dataset: entity Recall@10 0.80, numeric
Recall@10 1.00, and 3% entity lexical contribution. It did correctly constrain
both SQL arms, but did not improve this benchmark.

## Diagnostic comparison

The POST dense `full` arm scored all Recall@10 0.70 and entity Recall@10 0.70;
the contemporaneous hybrid arm scored 0.7667 and 0.80 respectively. Hybrid therefore
recovered one entity item relative to the dense arm in the same POST matrix, but it
still regressed against the ticket's required PRE comparison.

Adding the stored generated column rewrites the populated table and can rebuild the
IVFFlat index. The identical corpus and settings nevertheless produced different
approximate dense candidates between PRE and POST (PRE entity 1.00, POST dense 0.70).
That observed ANN variance is recorded, not used to replace the pre-registered
acceptance comparison.

## Delivered behavior

- Migration `030` adds generated `content_tsv` plus a GIN index, with a rollback.
- Dense and `websearch_to_tsquery` lexical arms each retrieve 15 candidates inside
  the same transaction and fuse with RRF `1 / (60 + rank)`.
- `category` is optional and parameterised on both arms; absent means no predicate.
- The 0.60 confidence threshold remains on the best dense cosine, never the RRF score.
- Lexical-only candidates expose `similarity: null`, never a fabricated zero.
- Prometheus exports hybrid mode and dense-only / lexical-only / both final-source hits.
- The dense-only path remains available and is the default because the targets missed.

## Verification

- GOA-137 ticket guards: 15 passed.
- Full RAG container suite: 286 passed, 2 skipped.
- Populated migration: apply, transactional rollback and reapply succeeded.
- Fresh database: migrations 001, 002, 017, 027 and 030 applied; generated value and
  GIN index verified; temporary database removed.
- Real API: category-filtered Chevening query ranked the hand-labelled source first;
  source arm provenance and Prometheus counters were present.
- Authenticated client flow: Gateway `/api/chat` → Orchestration `RAG` intent → RAG
  completed with a real signed JWT and streamed sources. A temporary runtime-only
  hybrid pass preserved source arm provenance through both proxies; RAG was then
  recreated at the committed default-off setting (`goa_rag_hybrid_enabled 0`).
- PostgreSQL `EXPLAIN ANALYZE` used `documents_content_tsv_idx` via Bitmap Index Scan.
