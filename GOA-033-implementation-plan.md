# GOA-033 — Implementation plan (RAG quality: re-ranking, source citation, confidence threshold)

**For Antigravity (implementer) and the project owner (reviewer), working together.**

Ticket: `GOA_Sprint_4_Tickets.md` line 352 — *"RAG quality improvements — re-ranking, source
citation, confidence threshold"*, P2, 2 story points.

**Verified against the `GOA` working tree on 2026-07-30 at commit `483d28d`.** Every claim below
was checked by reading the repository. Where a claim needs a running stack to confirm, it is
marked **[VERIFY]** and there is a command for it.

> [!IMPORTANT]
> **The 2-point estimate is wrong, and one of the ticket's own premises is probably wrong too.**
>
> The ticket frames BUG-051 as a **ranking** problem. The evidence in the repository points at an
> **approximate-index recall** problem instead: `documents` is indexed with `ivfflat (lists = 100)`
> and `ivfflat.probes` is never set anywhere in the codebase, so it defaults to **1**. One list out
> of a hundred is scanned per query.
>
> **A cross-encoder cannot re-rank a chunk that retrieval never returned.** If that diagnosis
> holds, the headline deliverable of this ticket does not fix the bug it was assigned. Trap 2.2
> has the diagnostic, and it is the first thing to run — before installing sentence-transformers,
> before writing any re-ranker code.
>
> Separately: the confidence threshold is **already written and completely inert** (trap 2.1), the
> RAG golden dataset is **50 rows of `"Dummy RAG question 1"`** so both eval DoD lines are
> currently unmeasurable (trap 2.3), and the `documents` table **has no `title` column** while the
> AC demands `{title, url, relevance_score}` from stored metadata (trap 2.4).
>
> Budget **6 points**, and expect the first one to go entirely into measurement.

---

## 0. How Antigravity must work this ticket — read this section twice

> [!CAUTION]
> **This section is a protocol, not advice. Every clause is binding.** If you are Antigravity and
> you are reading this, you do not get to compress, summarise, skim, or "proceed to the
> implementation." The protocol *is* part of the implementation.

### 0.1 Invoke the skeleton-mentor skill before writing anything

Load and follow `skeleton-mentor.skill.md`. Its rules govern this ticket. Restating the four that
bind hardest here:

- **Rule 1 — task granularity.** Every gap you leave is a *behaviour* task with constraints, never
  a fill-in-the-blank and never a vague "implement the re-ranker."
- **Rule 2 — density calibration.** State NEW vs REPEAT before scaffolding. Section 0.4 below
  already classifies each component; use those classifications and say them out loud in chat.
- **Rule 6 — no direct file writes for implementation code.** See 0.2. This is reinforced by an
  explicit instruction from the project owner for this ticket.
- **Rule 7 — tests are the exception.** You write test files directly, run them, and iterate to
  green. Small mechanical misses you fix yourself. A failure that reveals a real design gap in the
  owner's scaffolded logic goes back through rule 4's three-part feedback, not a silent patch.

### 0.2 Code goes in the chat, not into the files

**Do not use file-editing tools for implementation code in this ticket.** For every step:

1. Post the snippet **in the chat**, in a fenced block, with the target file path and the
   approximate line range as a heading above it.
2. State what it changes and what it deliberately leaves out.
3. **Stop. Wait for the owner** to apply it and say so.

The owner types the code. That is the point of the exercise. A snippet pasted into the chat that
the owner retypes teaches something; the same snippet written straight to disk teaches nothing.

Test files are the exception (rule 7) — write those directly and run them.

### 0.3 One step at a time, with a gate between each

Section 4 is a numbered sequence. For each step:

- Post the skeleton and the behaviour tasks in chat
- **Wait** for the owner
- When they say it is in, run the tests for that step and report
- Only then move to the next step

Do not batch two steps into one message. Do not post step 4 while step 3 is unresolved. If the
owner asks for the next step before the current one is verified, say that the current one is not
verified yet and what is outstanding.

### 0.4 Pattern classification — declare these in chat before scaffolding

| Component | Classification | Consequence |
|---|---|---|
| Cross-encoder re-ranking | **NEW** — first sentence-transformers model, first re-rank stage in the project | Sparse skeleton. Signatures, constraints, and the score-scale problem stated; the logic is the owner's |
| Confidence-threshold refusal contract | **NEW** — first endpoint in the project that refuses to answer | Sparse skeleton. The contract shape is given because it is an AC; the placement and the FAQ interaction are the owner's |
| Source-citation mapping | **REPEAT** — mapping persisted rows to a response contract is done in `program_requirements.py`, `visa.py`, `scholarship_programs.py` | Near-complete skeleton. Leave only the `title` sourcing decision as a task |
| Cache + Prometheus counters | **REPEAT** — this service already has four Prometheus collectors and a Redis client | Near-complete skeleton |
| Retrieval-quality eval harness | **NEW** — no retrieval-ranking metric exists anywhere | Sparse skeleton, and it is mostly a dataset problem, not a code problem |

The owner may override any of these with `"treat this as new"` / `"treat this as a repeat"`.

### 0.5 What you must not do

- Do not install `sentence-transformers` until **Step 1** is complete and the owner has seen the
  numbers. The diagnostic may change the design.
- Do not edit `evals/golden_dataset.json`'s `rag` array to make a metric move. Trap 2.3.
- Do not ask the LLM for a document title, or derive one from generated text. The AC forbids it in
  as many words: *"never generated or repaired by the LLM."*
- Do not report a step as done because its tests pass. Section 6 defines done.

---

## 1. Ground truth — what already exists

### 1.1 Retrieval and generation

| Thing | State | Location |
|---|---|---|
| pgvector cosine retrieval | ✅ | `app/services/rag_service.py:193–204` |
| Retrieval width | ⚠️ **top-5, not top-15.** `LIMIT $2` where `$2 = top_k`, default 5 | `rag_service.py:200`, `api/query.py:46` |
| `top_k` caller-controlled via `request.topK` | ⚠️ A caller sending `topK=3` starves any re-ranker | `app/schemas/query.py:10` |
| ANN index | ⚠️ `ivfflat (vector_cosine_ops) WITH (lists = 100)` | `app/migrations/017_reembed_dimensions.sql:5` |
| `ivfflat.probes` | ❌ **Never set anywhere in the repo.** Defaults to 1 | — |
| Embedding dimension | ✅ 768, `nomic-embed-text` via Ollama | migration 017 |
| Cross-encoder / `sentence-transformers` | ❌ Not in `requirements.txt`, not imported anywhere | — |
| FAQ short-circuit at 0.85 pg_trgm similarity | ✅ — returns before embedding, retrieval and LLM | `rag_service.py:122–138,165–176` |
| Hallucination guard | ⚠️ One soft sentence in the prompt | `rag_service.py:239` |
| W3C traceparent → Langfuse nesting | ✅ Landed in `372a2a5` | `api/query.py:30`, `app/core/trace_context.py` |

### 1.2 The confidence threshold — present and inert

`app/api/query.py:68–69`:

```python
if top_similarity < 0.6:
    LOW_CONFIDENCE_TOTAL.inc()
```

That is the entirety of it. It runs **after** `query_rag` has already embedded the question,
retrieved chunks, called the LLM and returned an answer. It increments a counter and changes
nothing. See trap 2.1.

### 1.3 The response contract

`app/schemas/query.py`:

```python
class DocumentSource(BaseModel):
    id: str
    content: str
    source_url: Optional[str]
    similarity: float

class QueryResponse(BaseModel):
    answer: str                      # <-- required, non-nullable
    sources: List[DocumentSource] = []
```

The AC requires `sources: [{title, url, relevance_score}]` and
`{answer: null, reason: "insufficient_data", suggestion: "..."}`. **Neither shape is expressible
in the current schema.** `title` has no column to come from (trap 2.4), `answer` cannot be null,
and `reason` / `suggestion` do not exist.

### 1.4 The `documents` table

`app/migrations/002_create_documents.sql`, as amended by `017`:

```sql
CREATE TABLE IF NOT EXISTS documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    content TEXT NOT NULL,
    embedding VECTOR(768),
    source_url VARCHAR(255),
    category VARCHAR(100),
    last_updated TIMESTAMP DEFAULT NOW()
);
```

**No `title`.** No metadata JSONB. `source_url` is `VARCHAR(255)`, which is worth noting
separately — MastersPortal URLs run long and a truncating insert would silently corrupt citations.
**[VERIFY]** whether any stored `source_url` is exactly 255 characters.

### 1.5 Metrics and cache

| Thing | State |
|---|---|
| `goa_rag_query_latency_ms{cache_hit}` | ✅ — but `cache_hit` is **hardcoded `"false"`** at `api/query.py:63,79` |
| `goa_rag_retrieval_similarity_score` | ✅ |
| `goa_rag_low_confidence_total` | ✅ — increments, refuses nothing |
| `goa_rag_cache_hits_total` | ❌ Does not exist |
| `goa_rag_requests_total` | ❌ Does not exist |
| A query cache | ❌ Does not exist — **but `app/core/redis.py` connects and logs `"Connected to Redis for RAG cache."`** |
| `retrieval_score` (avg similarity of *used* chunks) | ❌ Only `top_similarity` is logged, not the average |

### 1.6 The eval harness

| Thing | State |
|---|---|
| `evals/golden_dataset.json` → `rag` array | ⚠️ **50 items, all `"Dummy RAG question N"` with `"concept_a_N"` placeholders** |
| `run_rag_eval` | ⚠️ End-to-end answer-concept check judged by `claude-3-haiku-20240307`, keyed off `ANTHROPIC_API_KEY` |
| `relevant@1` or any retrieval-ranking metric | ❌ Does not exist |
| Ground-truth chunk IDs per question | ❌ Do not exist — so relevant@1 is not computable from this dataset |

**So the real work is:** measure why retrieval misses before building the thing meant to fix it;
give the corpus a citable title; make the threshold actually refuse, before the LLM call, without
breaking the FAQ path or Orchestration; build a retrieval metric and a real dataset so "≥5%" means
something; then add the re-ranker and prove it moved that metric.

---

## 2. Traps

### 2.1 🔴 The confidence threshold is already written and does nothing

Both the AC and the implementation note are explicit about ordering:

> *"Confidence threshold: if top chunk similarity score < 0.6, return `{answer: null, reason:
> "insufficient_data", suggestion: "..."}`"*
> *"Similarity threshold check **before** LLM call."*

What is implemented is a counter increment after the answer has been generated and is about to be
returned (`api/query.py:68`). The user gets an answer built from chunks the service has just
formally recognised as too weak to answer from, and `goa_rag_low_confidence_total` ticks up to say
so.

**This is the ticket's cleanest example of green meaning nothing.** The metric exists. The metric
increments. The metric appears on a dashboard. A test asserts that it increments (trap 2.8). And
the behaviour the metric is named for was never built.

Three consequences for the work:

- The threshold check has to move **into `query_rag`**, between retrieval and prompt construction
  — not into `query.py`, where it currently sits downstream of everything it is supposed to gate.
- Moving it saves an LLM call on every low-confidence query, which is the entire cost argument for
  the feature.
- `0.6` was calibrated against a near-empty corpus, per the ticket's own Option B note, and the
  IELTS adapter has since gone from one page to five (`f5e666e`). **The number is a variable to
  re-derive, not a constant to preserve.** Put it in config.

### 2.2 🔴 BUG-051 is probably not a ranking problem, and the assigned fix cannot solve it

The ticket's evidence:

> Asked *"How many questions are in the IELTS Reading test?"*, RAG returned a mastersportal
> programme card at 0.591 and answered "I do not know." The very next query in the same run
> retrieved the answering chunk at **0.774**.

Read that carefully. The answering chunk scores **0.774** against a *related* query and is not in
the top-5 for the *direct* query. If this were a ranking problem, the chunk would be retrieved and
mis-ordered — it would appear at position 3 or 4 with a decent score. Instead it is **absent**.

Now the index:

```sql
CREATE INDEX documents_embedding_idx ON documents
  USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
```

`ivfflat` is an **approximate** index. It partitions vectors into `lists` clusters and, at query
time, scans only `ivfflat.probes` of them. **`probes` is never set anywhere in this repository**,
and pgvector's default is `1`.

So each query scans **1 of 100 partitions**. With a corpus in the low thousands of rows, that is
roughly a 1% scan. Whether the right chunk is found depends on whether it happens to sit in the
one cluster nearest the query vector — which is exactly the "found for one phrasing, missed for a
near-identical phrasing" behaviour the bug describes.

And `lists = 100` is itself too aggressive for this corpus. pgvector's guidance for under a
million rows is roughly `rows / 1000`. At ~3,000 rows that is `lists ≈ 3`, not 100. The index was
built for a corpus a hundred times larger than the one it holds.

**A cross-encoder re-ranks candidates. It cannot resurrect a candidate the index never returned.**
If this diagnosis holds, building the re-ranker first means shipping the ticket with BUG-051 still
open and a plausible-looking re-ranker sitting on top of a 1% recall floor.

**Step 1 exists to settle this before anything else is built.** Run this against the real corpus:

```sql
-- The candidate the bug says exists. Find its exact id and its true cosine rank.
SET LOCAL ivfflat.probes = 1;
EXPLAIN (ANALYZE, BUFFERS) SELECT id, source_url, 1 - (embedding <=> $1::vector) AS sim
FROM documents ORDER BY embedding <=> $1::vector LIMIT 15;

-- Same query, exact scan. Sequential scan = ground truth, no approximation.
SET LOCAL enable_indexscan = off;
SET LOCAL enable_bitmapscan = off;
SELECT id, source_url, 1 - (embedding <=> $1::vector) AS sim
FROM documents ORDER BY embedding <=> $1::vector LIMIT 15;
```

**If the exact scan returns the IELTS chunk and the indexed scan does not, the bug is recall, the
fix is index configuration, and the re-ranker is a separate improvement rather than the fix.** Say
so in chat, in those words, and let the owner decide (3.1).

Note also: an exact scan over a few thousand 768-dimensional vectors is sub-100 ms. For this
corpus size, **dropping the ANN index entirely** is a legitimate option and removes a whole class
of nondeterminism from every measurement this ticket depends on.

### 2.3 🔴 The RAG golden dataset is placeholder data, so both eval DoD lines are unmeasurable

`evals/golden_dataset.json`, `rag` array, 50 items, every one of this shape:

```json
{ "question": "Dummy RAG question 1",
  "expected_answer_concepts": ["concept_a_1", "concept_b_1"] }
```

Two DoD lines depend on this:

- *"Eval: re-ranking improves golden dataset accuracy from baseline by ≥5%"*
- *"Eval: re-ranking on 10 golden dataset queries improves relevant@1 metric vs non-reranked
  baseline"*

Neither is currently measurable, and the failure is worse than "no signal":

1. **`run_rag_eval` grades by asking a judge whether the answer contains `"concept_a_1"`.** Nothing
   in the corpus contains that string, so every item fails. Baseline accuracy is ~0, and any
   perturbation looks like movement.
2. **There is no `relevant@1` metric in the harness at all.** It is an end-to-end answer-concept
   check, not a retrieval-ranking measure. Computing relevant@1 requires knowing which chunk *is*
   the right answer for each question — ground-truth document IDs the dataset does not have.
3. **`run_rag_eval` scores infrastructure failures as accuracy drops.** `runner.py:266–268`: on an
   httpx exception it sets `service_data = {}`, then asks the judge whether `{}` contains the
   concepts. A RAG outage reads as a quality regression. And at `runner.py:284–285`, a judge
   exception is `except Exception: pass` — the item silently counts as a failure.
4. **It hardcodes `claude-3-haiku-20240307` and reads `ANTHROPIC_API_KEY` directly**, bypassing
   `ANTHROPIC_BASE_URL`. Under AgentRouter this either fails or bills a different provider than
   the rest of the system.

**You cannot demonstrate a ≥5% improvement against dummy data.** Building a real dataset is part
of this ticket, it is the least glamorous part, and everything measurable depends on it. Decision
3.3 sizes it.

### 2.4 🔴 The AC requires a `title` the database does not store

AC: *"every answer includes `sources: [{title, url, relevance_score}]` **assembled from stored
document metadata, never generated or repaired by the LLM**."*

`documents` columns: `id, content, embedding, source_url, category, last_updated`. **There is no
title, and no metadata column to hide one in.**

The forbidden shortcut is the obvious one — ask the model for a title, or slice the first line of
`content`. The AC's clause exists precisely because a generated title is a citation that claims
provenance it does not have. Content-slicing is marginally better but still synthesises a claim
about the source from the chunk body.

The honest options, all of which need a decision (3.2):

1. **Add a `title` column, populate it at ingest** from what the adapter actually saw — the HTML
   `<title>`, the card's programme name. Correct, and it makes this ticket depend on an ingestion
   change plus a backfill for ~3,000 existing rows.
2. **Derive deterministically from `source_url` + `category`** — no new column, no LLM, honest
   about what it is, and produces citations like *"ielts.org — band_descriptors"*. Weakest as a
   user-facing label, strongest on provenance.
3. **Return `title: null` where unknown** and let the frontend fall back to the URL. Truthful,
   and it makes the AC's own field vestigial.

Option 1 is right and costs the most. Whichever is chosen, **write down why**, because "where did
this title come from" is exactly the question a reviewer will ask.

### 2.5 🟠 Retrieval is top-5, and the re-ranker needs top-15

AC: *"after initial retrieval of top-15 chunks, use cross-encoder to re-rank and return top-5."*

`rag_service.py:200` — `LIMIT $2`, bound to `top_k`, default 5. `api/query.py:46` —
`top_k=request.topK or 5`.

So today the service retrieves exactly what it returns. Two distinct numbers are needed —
a **retrieval width** and a **return width** — and they are currently one variable with one name.

The trap inside the trap: `topK` is **caller-controlled** and unvalidated. A caller sending
`topK=3` would give the re-ranker three candidates. A caller sending `topK=500` would put 500 pairs
through a CPU cross-encoder inside a request. Decide whether `topK` means "candidates to retrieve"
or "sources to return" — it cannot keep meaning both — and clamp it.

### 2.6 🟠 The FAQ path returns zero sources, and puts a string similarity in the vector-similarity field

`rag_service.py:165–176`. On an FAQ hit the function returns early with:

```python
"top_similarity": float(faq_match["sim"]),   # <-- pg_trgm trigram similarity
...
return faq_match["answer_markdown"], [], metrics_summary   # <-- empty sources
```

Two problems, and the second one is subtle enough to survive review.

**First:** `sources` is `[]`. The AC says *"every answer includes `sources`."* An FAQ answer
currently includes none. Curated FAQ rows have no document provenance, so either they get a
synthetic "curated answer" citation, or the AC gets an explicit documented exception. Pick one.

**Second, and this is the one to watch:** `top_similarity` is set to a **pg_trgm trigram string
similarity** — how alike two *strings* look. Everywhere else in this service the same field holds a
**cosine similarity between embeddings**. Two incomparable metrics, one field name, one downstream
threshold.

`FAQ_SIMILARITY_THRESHOLD` is 0.85, so every FAQ hit carries `top_similarity >= 0.85` and sails
past a 0.6 vector threshold — **for entirely the wrong reason**. It gets the right answer by
coincidence, and the coincidence holds only while the FAQ threshold stays above the confidence
threshold. Lower `FAQ_SIMILARITY_THRESHOLD` to 0.5 some day and FAQ answers start being refused by
a check that has no business evaluating them.

Separate the fields, or short-circuit the threshold explicitly on the FAQ path. Do not leave two
metrics sharing a name.

### 2.7 🟠 The refusal contract breaks Orchestration, and `.get()` will not save it

`services/orchestration/app/services/client.py:267` and `:312`:

```python
answer = data.get("answer", "No answer received.")
```

That default fires when the key is **absent**. If RAG returns `{"answer": null, "reason": ...}`,
the key is present with value `None`, so `.get` returns `None` — and `None` flows into the SSE
token stream as answer content.

**[VERIFY]** what the frontend renders for a `null` token: the string `"None"`, an empty bubble, or
a thrown error.

So the refusal contract is a **cross-service change**, exactly like GOA-026's tier enforcement
turned out to be. Orchestration must learn to recognise a refusal and surface it as something
deliberate. Decide the wire shape in 3.4 and change both sides in this ticket, or the feature works
in isolation and breaks the only path a user can reach it through — which the ticket's cohesion
requirement forbids.

### 2.8 🟠 An existing test asserts the current wrong behaviour

`services/rag/tests/test_query.py:158` — `test_low_similarity_increments_metrics_counter`:

```python
assert response.status_code == 200
...
assert val_after == val_before + 1.0
```

It asserts that a low-similarity query returns **200 with an answer** and bumps the counter. That
is a green test encoding the defect in 2.1.

When the threshold starts refusing, this test fails. **The correct response is to rewrite the
test**, not to soften the refusal so the test keeps passing. Say so in chat when it goes red, and
name it as expected — otherwise it reads like a regression you caused.

This is the ticket's own warning list in action: *"A profile-sync test asserted the exact wrong
timestamp, pinning the bug in place."* Same shape, different file. GOA-041 had one too.

### 2.9 🟠 There is no cache, and the logs say there is

`app/core/redis.py:18` logs **`"Connected to Redis for RAG cache."`** on startup. The client
connects. It pings. Nothing in `query_rag` reads or writes it.

Meanwhile `api/query.py:63` and `:79` hardcode `cache_hit="false"`, with
`# TODO: Update in GOA-015 once caching is implemented` — a TODO pointing at a Sprint 2 ticket
that shipped.

So: a startup log announcing a cache, a metric label permanently reporting misses, and no cache.
The AC wants `goa_rag_cache_hits_total` vs `goa_rag_requests_total` — **neither collector exists**.

If you add the counters without adding the cache, `cache_hits_total` sits at zero forever and the
ratio panel reads 0%, which is indistinguishable from a cache that is present and useless. Add
both, or add neither and say so.

### 2.10 🟠 `relevance_score` and the 0.6 threshold are on different scales

This one is a category error waiting to happen, and it will not announce itself.

`cross-encoder/ms-marco-MiniLM-L-6-v2` outputs an **unbounded logit**, conventionally in roughly
`-11 … +11`. It is not a probability and it is not a similarity. Cosine similarity from pgvector is
in `0 … 1`.

Now put both through this ticket's requirements:

- AC: `sources: [{..., relevance_score}]` — which scale?
- AC: `if top chunk similarity score < 0.6` — a cross-encoder logit of `0.6` is a middling-to-poor
  score, whereas a cosine similarity of `0.6` is the calibrated floor. **The same number means
  opposite things.**
- BUG-052's evidence quotes scores like `0.798`, `0.783` — those are cosine values from the current
  system, so any re-tuning against them is re-tuning the cosine threshold, not a re-ranker one.

Decide explicitly (3.5): threshold on **pre-rerank cosine** and expose cosine as
`relevance_score`; or threshold on a **sigmoid-normalised** cross-encoder score with its own
separately calibrated constant. Do not let a cross-encoder logit reach a comparison written for
cosine — the failure mode is a threshold that silently never triggers, or one that refuses
everything.

### 2.11 🟠 BUG-052 needs a "does this source support the claim" test the codebase does not have

BUG-052: for *"What does band 7 mean?"*, sources ranked `[0] 0.798 contains-claim=False`,
`[1] 0.783 True`, `[2] 0.781 True`.

Note what `contains-claim` is: **a judgement about whether a chunk supports the generated answer**,
which is only computable *after* generation. The AC's options are *"order or filter cited sources
by whether they actually support the generated answer, rather than by raw similarity, or cite
per-claim."*

Every one of those requires a support check that does not exist in this repo. The choices, in
rising cost:

1. **Lexical overlap** between answer and chunk — cheap, deterministic, easy to test, and weak on
   paraphrase.
2. **Cross-encoder scored on (answer, chunk)** rather than (question, chunk) — reuses the model
   you are already adding, and is a genuinely good fit.
3. **A second LLM call** to attribute claims to sources — most accurate, adds latency and cost to
   every answer, and is a new call site the AgentRouter budget has to absorb.

Option 2 is the one to recommend, and it makes the re-ranker do double duty. **Note the ordering
constraint it implies:** re-rank (question, chunk) *before* generation to pick context, then score
(answer, chunk) *after* generation to order citations. Two scoring passes, two different input
pairs, one model. Getting this backwards produces citations ordered by question-relevance, which is
what BUG-052 already complains about.

### 2.12 🟡 The cross-encoder is a runtime download and a latency cost

`sentence-transformers` will pull `ms-marco-MiniLM-L-6-v2` (~90 MB) from HuggingFace **on first
use**, into `~/.cache/huggingface`. In a container that means: a cold-start network dependency on
huggingface.co, a slow first request, and a hard failure in any environment without egress.

Bake it into the image at build time and set `HF_HOME` / `TRANSFORMERS_OFFLINE` deliberately.

**Latency:** 15 pairs through a 6-layer cross-encoder on CPU is real time — tens to low hundreds of
milliseconds, and it is **serial with** retrieval and generation. RAG sits inside an SSE path with a
25 s LLM timeout above it (`rag_service.py:40`). Measure it, and load the model **once at startup**,
not per request. A `CrossEncoder(...)` constructed inside `query_rag` reloads the model on every
query and will look like a re-ranker that works and is inexplicably slow.

### 2.13 🟡 `retrieval_score` is specified as an average and only the max is computed

AC: *"Answer quality metric logged: `retrieval_score` (avg similarity of used chunks)."*

`rag_service.py:207–219` computes `top_similarity` as a running **maximum**. There is no average
anywhere, and `metrics_summary` carries no `retrieval_score` key.

After re-ranking, "used chunks" means the top-5 that survived, not the 15 retrieved — so the
average has to be taken at the right point in the pipeline, over the right set, on a decided
scale (2.10).

### 2.14 🟡 Cost is reported at the wrong model's prices

`rag_service.py:274–275`:

```python
# Estimated cost calculation for claude-haiku-4-5-20251001 ($0.25/M input, $1.25/M output tokens)
cost_usd = (input_tokens * 0.25 + output_tokens * 1.25) / 1_000_000
```

`settings.llm_model` is `claude-opus-4-8` and the AgentRouter published rates are $2 / $10 per 1M.
Every Langfuse cost figure from RAG is understated by roughly **8×**.

`2fadba4 feat(costs): aggregate daily model-aware usage` made the shared cost path model-aware.
This literal remains. Out of scope to fix properly here, but you are editing this function — flag
it, and prefer the shared helper over the literal if it is a one-line substitution.

### 2.15 🟡 Raw scraped content is interpolated straight into the prompt

`rag_service.py:232–247` builds `context_str` from `row["content"]` with no delimiting, no escaping,
and no instruction boundary. That content came from scraped third-party web pages via the ingestion
adapters.

A page containing *"Ignore previous instructions and…"* is inside the instruction context. That is
GOA-034's territory formally, and this ticket is rewriting the prompt anyway. At minimum, delimit
the context explicitly and put the hallucination guard **after** it, so injected text cannot
trivially override a guard that precedes it. Note it for GOA-034 rather than solving it here.

---

## 3. Decisions to make before coding

Antigravity: post these five in chat with your recommendation, and **wait for the owner's answer on
3.1 and 3.3 before writing any code.** 3.2, 3.4 and 3.5 can be answered at their step.

### 3.1 Is BUG-051 a recall problem or a ranking problem? (settle empirically — Step 1)

**Recommendation: measure first, then decide, and expect recall.**

If the exact scan finds the chunk and the indexed scan does not: fix the index — raise
`ivfflat.probes`, rebuild with `lists ≈ rows/1000`, or drop the ANN index for a corpus this size —
and re-scope the re-ranker as a quality improvement with BUG-051 closed separately.

If both scans miss it: the bug is embedding or chunking, not ranking, and the re-ranker will not
fix it either. Escalate to the owner before proceeding — that is a different ticket.

If the indexed scan finds it and merely ranks it below a mastersportal card: the ticket's original
premise holds and the cross-encoder is the right fix.

**Do not skip this because the ticket already told you it is a ranking problem.** The ticket says
*"worth investigating as a ranking problem"* — investigating, not assuming.

### 3.2 Where does `title` come from?

**Recommendation: option 1 — add a `title` column, populate at ingest, backfill existing rows.**

It is the only option that makes the citation's title mean what a user assumes it means. Migration
`027_add_documents_title.sql`, populated by the ingestion adapters from what they actually parsed,
with a backfill deriving from `source_url` for existing rows and `NULL` where nothing is known.

`title` must be **nullable**, and the response must tolerate null rather than substituting a
placeholder — an invented title is exactly what the AC forbids.

If the owner judges the ingestion change out of scope, option 2 (deterministic from
`source_url` + `category`) is acceptable **provided the PR says the title is derived, not
recorded.** Do not present a derived title as a stored one.

### 3.3 How big is the real golden dataset, and who writes it?

**Recommendation: 15 hand-written questions with ground-truth chunk IDs, written by the owner, not
generated.**

Ten is the AC's floor for the relevant@1 line; 15 gives a little headroom against a single
question dominating the percentage. Each item needs:

```json
{ "question": "How many questions are in the IELTS Reading test?",
  "relevant_document_ids": ["<uuid>"],
  "expected_answer_concepts": ["40 questions"] }
```

**Include BUG-051's and BUG-052's queries as items.** They are the two cases the ticket exists to
fix; they belong in the dataset that proves it.

`relevant_document_ids` has to be obtained by querying the real corpus and reading the chunks —
which is why this is the owner's task, not a generation task. A generated dataset would encode
whatever the current system already does, and measure nothing.

Keep the existing 50 dummy items or delete them, but **do not let them into the metric.** If they
stay, key the new metric off a separate array (`rag_retrieval`) so the dummy rows cannot dilute it.

### 3.4 What does a refusal look like on the wire?

**Recommendation: `200` with `{answer: null, reason, suggestion, sources: [...]}`.**

Not a 4xx — the request was well-formed and the service worked correctly. A refusal is a valid
answer to "what do you know about this," and an error status would make Orchestration's exception
path swallow it.

**Keep `sources` populated even on refusal.** The user is better served by "I could not answer, but
here is what I found and how weak it was" than by an empty response — and it makes the refusal
debuggable in Langfuse.

Orchestration must then map a null answer onto a deliberate SSE event rather than streaming `None`
(2.7). Mirror the `subscription_required` pattern `6fba90c` established for GOA-026 — that is the
project's existing convention for "the service declined, deliberately."

### 3.5 Which scale does `relevance_score` use, and what does the threshold compare?

**Recommendation: threshold on pre-rerank cosine; expose cosine as `relevance_score`; keep the
cross-encoder score as a separate internal field.**

Reasons: the 0.6 constant and BUG-052's quoted numbers are cosine values, so cosine keeps the
calibration work interpretable; cosine is bounded 0–1 so a frontend can colour-code it; and
thresholding before the re-ranker means a refused query never pays for the cross-encoder either.

If the owner prefers thresholding on the cross-encoder score, then it **must** be
sigmoid-normalised and it needs its own constant, separately calibrated, with a different name than
`0.6`. Do not reuse the number.

---

## 4. Implementation — step by step

> [!CAUTION]
> **Protocol reminder (0.2, 0.3).** Every snippet below goes **in the chat**. The owner types it.
> One step per message. Wait for confirmation before the next. Tests are yours to write and run
> directly (skeleton-mentor rule 7).

### Step 1 — Measure. Write no feature code. **[gate: owner sees the numbers]**

Nothing in this ticket is calibratable until the corpus is characterised. Produce, in chat:

1. `SELECT count(*) FROM documents;` and a breakdown by `category` and by `source_url` host.
2. The 2.2 diagnostic — indexed vs exact scan for BUG-051's question — with both result sets side
   by side.
3. The same for BUG-052's *"What does band 7 mean?"*, recording `contains-claim` by hand for the
   top 5.
4. The current cosine-similarity distribution: `min`, `p25`, `median`, `p75`, `max` of
   `top_similarity` across the 15 questions from 3.3.
5. **A recommendation on 3.1**, in one paragraph, naming which of the three outcomes you observed.

Then stop. Post it and wait.

Point 4 is what re-derives `0.6`. The Option B note says the threshold was set against a near-empty
corpus and the IELTS adapter has since quintupled; a threshold nobody re-measured is a guess with a
decimal point.

### Step 2 — Fix retrieval recall, if Step 1 says to. **[gate]**

Only if 3.1 came back "recall." Scope by what Step 1 showed:

- `SET LOCAL ivfflat.probes = N` on the retrieval connection — a `SET LOCAL` inside the same
  transaction as the query, not a global, so it cannot leak across pooled connections
- and/or migration `027` rebuilding the index with `lists` appropriate to the real row count
- and/or dropping the ANN index, if Step 1 shows an exact scan is fast enough at this corpus size

**Behaviour task, not a value to paste:** determine `probes` empirically. Increase it until the
indexed top-15 matches the exact top-15 for all 15 dataset questions, then record the latency cost
at that setting. The deliverable is a number *with the measurement that justifies it* — a `probes`
value with no recall curve behind it is the same guess as the `0.6`.

Re-run Step 1's point 2 afterwards and show the before/after in chat. **If BUG-051 closes here,
say so explicitly** — that is a significant finding about the ticket, not a footnote.

**Benchmark gate:** before changing anything, put the index setting behind `RAG_IVFFLAT_PROBES`
(4B.1) and capture `baseline` and `probes-only` (4B.5). This pair is the evidence for 3.1, and it
is the only moment in the ticket when the pre-fix system still exists to measure.

### Step 3 — The golden dataset and a real retrieval metric. **[gate]**

Per 3.3. The owner writes the 15 items; you build the harness.

New: `evals/rag_retrieval_eval.py`. Sparse skeleton (NEW pattern) — signatures and constraints
only:

```python
def relevant_at_1(results: list[str], relevant_ids: set[str]) -> float:
    """1.0 if results[0] is in relevant_ids, else 0.0.

    TODO (owner): decide and implement the empty-results case. A query that
    retrieved nothing is not the same as a query whose top hit was wrong, and
    the refusal path in Step 5 will produce empty results by design. Whatever
    you choose, the docstring must say it and a test must assert it.
    """
```

Behaviour tasks to leave, at rule-1 granularity:

- `TODO`: compute recall@15 alongside relevant@1. relevant@1 alone cannot distinguish "re-ranking
  improved ordering" from "retrieval found more candidates" — and after Step 2 you need to know
  which one moved.
- `TODO`: run every question through both paths in a single invocation — retrieval-only and
  retrieval-plus-rerank — and emit both scores. Two separate runs against a live LLM and a live
  corpus are not comparable; anything that changes between them contaminates the delta.
- `TODO`: fail loudly and distinguishably when the RAG service is unreachable. `runner.py:266`
  scores an outage as a quality drop (2.3); do not reproduce that. An infrastructure failure must
  exit non-zero with a different message than a quality regression.

Then record the **baseline** — pre-rerank relevant@1 and recall@15 — and put the numbers in chat.
The ≥5% claim is meaningless without a number to be 5% above, and that number must be measured
after Step 2, since Step 2 moves it.

### Step 4 — `title`, and the citation contract. **[gate]**

Per 3.2. REPEAT pattern — near-complete skeleton is appropriate here; the only genuine task is the
title sourcing.

- Migration `027_add_documents_title.sql` — nullable `title`, plus the matching
  `rollback/027_..._down.sql`, following the convention every other migration in that directory
  uses.
- `DocumentSource` gains `title: Optional[str]` and `relevance_score: float`. **Decide whether
  `similarity` and `content` stay.** `content` in particular is a full chunk body in every
  citation of every response — check whether the frontend uses it before you keep paying for it on
  the wire.
- The mapping in `api/query.py:84–92` reads persisted columns only. **No fallback that invents a
  title.** `None` is a valid title.
- Ingestion populates it going forward; backfill existing rows in the migration.

**Behaviour task:** `source_url` is `VARCHAR(255)` (1.4). Determine whether any existing row is
exactly 255 characters, and if so decide whether this migration widens it. A citation URL truncated
at 255 characters is a link that 404s — and it looks completely correct in the response body.

### Step 5 — The threshold refusal, in the right place. **[gate]**

The core correctness fix (2.1). NEW pattern — sparse skeleton.

Constraints, all binding:

- The check lives **inside `query_rag`**, after retrieval, **before** `context_str` is built and
  before `_invoke_llm_with_retry`. If an LLM call happens on a refused query, the check is in the
  wrong place.
- Threshold from config, not a literal. Default from Step 1's measurement, not from `0.6`.
- The FAQ path must not be evaluated by it (2.6) — and the reason has to be *deliberate*, not the
  accident that `FAQ_SIMILARITY_THRESHOLD` happens to sit above it.
- The refusal still returns `sources` and still records `retrieval_score`, per 3.4.
- Delete the now-dead check at `api/query.py:68`, and keep `LOW_CONFIDENCE_TOTAL` incrementing at
  the new site. A counter in two places double-counts; a counter in neither is worse.

**Behaviour task:** `suggestion` is a user-facing string in the AC with no specified content.
Decide what it says and where it comes from — a config default, or something derived from the
question. Constraint: it must not name chunks that failed the threshold, because that is
recommending the sources you just declined to trust.

Then the cross-service half (2.7): Orchestration recognises the refusal and emits a deliberate SSE
event. Mirror `subscription_required` from `6fba90c`.

### Step 6 — The re-ranker. **[gate]**

Only now. NEW pattern — sparse skeleton, and the logic is entirely the owner's.

```python
# services/rag/app/services/reranker.py
class Reranker:
    """Cross-encoder re-ranking over retrieved candidates.

    TODO (owner): load CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2") ONCE,
    at application startup, and hold it here. A model constructed per request
    reloads ~90 MB of weights on every query -- the re-ranker will appear to work
    and be inexplicably slow. Wire the lifecycle into main.py's existing startup
    hook alongside redis_client.connect().

    TODO (owner): scores are unbounded logits, not similarities (see plan 2.10).
    Decide what this class returns and name it so no caller can mistake it for a
    cosine value.
    """

    def rank(self, query: str, candidates: list[dict], top_n: int) -> list[dict]:
        """TODO (owner): score every (query, candidate['content']) pair, sort
        descending, return the top_n.

        Constraints:
        - Preserve every key already on each candidate dict. Downstream code reads
          id, source_url, similarity; dropping one breaks citations silently.
        - Batch the pairs into a single predict() call. One call per candidate is
          15x the model overhead for identical output.
        - On any exception: log a warning, return candidates[:top_n] unchanged, and
          increment a rerank-failure counter. A re-ranker outage must degrade to
          plain cosine ordering, never fail the query -- but it must be VISIBLE,
          because a silent fallback is a re-ranker that quietly stopped working.
        """
```

Then:

- Split retrieval width from return width (2.5): retrieve 15, re-rank, return 5. Both configurable.
  Clamp `topK` and decide which of the two it means.
- Bake the model into the Docker image at build time (2.12); set `TRANSFORMERS_OFFLINE`
  deliberately so a missing cache fails loudly at startup rather than on the first user query.
- Re-run Step 3's harness. **Report MRR, relevant@1 and recall@15, before and after, in chat.** If
  the improvement is under 5%, say the number — do not adjust the dataset to reach the target. A
  ≥5% claim that required dataset edits is not a result.

**Benchmark gate:** capture `width-only` and `rerank` (4B.5). Widening retrieval and re-ranking are
two separate changes landing in one step, and only the `width-only` row can tell you which of them
moved the metric.

### Step 7 — Citation ordering for BUG-052. **[gate]**

Per 2.11, recommendation option 2: score `(answer, chunk)` after generation and order citations by
that, not by question-relevance.

**The ordering constraint is the whole trap here:** re-rank on `(question, chunk)` before
generation to choose context; score on `(answer, chunk)` after generation to order citations. Two
passes, two different input pairs, one loaded model. Reverse them and you have re-implemented the
bug.

**Behaviour task:** decide whether a chunk that scores below a support floor is **reordered** or
**dropped** from `sources`. Constraint: whatever you choose, a chunk that was in the LLM's context
and is *not* in the citations means the answer was influenced by something the user cannot see.
That may be the right trade — argue it either way, but argue it.

Verify against BUG-052's exact query. `contains-claim` for `sources[0]` must be `True`.

### Step 8 — Cache, counters, `retrieval_score`. **[gate]**

REPEAT pattern — near-complete skeleton.

- `goa_rag_requests_total` and `goa_rag_cache_hits_total` in `app/core/metrics.py`, following the
  existing collector style.
- An actual cache using the already-connected `redis_client` (2.9). Key on the normalised question
  plus anything that changes the answer — model, threshold, retrieval width. A cache keyed on the
  question alone serves pre-tuning answers after every re-calibration.
- Replace the hardcoded `cache_hit="false"` at `api/query.py:63,79` and delete the stale
  `# TODO: Update in GOA-015` comment.
- `retrieval_score` as the **mean** similarity of the chunks actually used (2.13), on the scale
  decided in 3.5.

**Behaviour task:** decide whether refusals are cached. Constraint: caching a refusal means a
corpus improvement does not take effect until the TTL expires; not caching it means a hammered
bad query pays full retrieval cost every time. State the TTL and why.

### Step 9 — The hallucination guard and the prompt. **[gate]**

- Delimit `context_str` explicitly so chunk text cannot be read as instruction (2.15).
- Put the guard **after** the context, not before it.
- Strengthen it from *"say that you do not know"* to answering only from provided context.
- Note the injection surface for GOA-034 in the PR. Do not try to solve prompt injection here.

**Behaviour task:** the guard's wording is testable. Write the instruction such that a test can
present context that does not contain the answer and assert refusal — then make that test exist.

---

## 4B. Benchmarking — capturing the before/after honestly

> [!IMPORTANT]
> **This section exists because the numbers are going on a CV.** That raises the bar above the
> ticket's own DoD. A DoD checkbox needs the metric to move. A CV claim needs to survive
> *"how did you measure that, and what was your sample size?"* from someone who has run
> benchmarks before and is mildly suspicious of yours.
>
> Everything below is designed around that second question.

### 4B.1 The design decision that makes this possible: flags, not branches

**Put every optimisation behind a config flag before benchmarking anything.**

```
RAG_RERANK_ENABLED        (default false until Step 6 ships)
RAG_THRESHOLD_ENABLED     (default false until Step 5 ships)
RAG_CACHE_ENABLED         (default false until Step 8 ships)
RAG_RETRIEVAL_WIDTH       (5 = pre-ticket behaviour, 15 = post)
RAG_IVFFLAT_PROBES        (1 = pre-ticket default, N = post)
```

Without flags, measuring "before" means `git stash`, rebuild, measure, unstash, rebuild, measure —
across two builds, two container restarts, and potentially two machine states. Every one of those
is a confound, and none of them is visible in the result.

With flags, before/after is **one binary, one corpus, one session, one config change**. That is the
difference between a comparison and two separate measurements you are hoping are comparable.

It also means the benchmark is a **matrix**, which is more informative than a pair:

| Run | probes | width | rerank | threshold | What it isolates |
|---|---|---|---|---|---|
| `baseline` | 1 | 5 | off | off | The system as it exists today |
| `probes-only` | N | 5 | off | off | **How much of the fix was the index** (2.2) |
| `width-only` | N | 15 | off | off | Whether widening alone helps |
| `rerank` | N | 15 | on | off | The cross-encoder's actual contribution |
| `full` | N | 15 | on | on | Shipped configuration |

That table is the whole argument. If `probes-only` captures most of the improvement, you learned
something real about the ticket, and saying so is worth more than a bigger headline number.

### 4B.2 The harness

New: `evals/rag_benchmark.py`, wrapping Step 3's `rag_retrieval_eval.py` and adding latency, cost
and stability. One command, one committed artifact:

```bash
python evals/rag_benchmark.py --label baseline --out evals/benchmarks/
```

Artifact shape — every field is there because its absence is a question an interviewer asks:

```json
{
  "label": "baseline",
  "captured_at": "2026-07-30T18:22:04Z",
  "fingerprint": {
    "git_sha": "483d28d",
    "corpus_rows": 3012,
    "corpus_checksum": "sha256 of sorted document ids",
    "ivfflat_lists": 100,
    "ivfflat_probes": 1,
    "embedding_model": "nomic-embed-text",
    "llm_model": "claude-opus-4-8",
    "retrieval_width": 5,
    "return_width": 5,
    "rerank_enabled": false,
    "threshold_enabled": false,
    "cache_enabled": false,
    "confidence_threshold": null
  },
  "quality":   { "n": 40, "recall_at_15": 0.0, "relevant_at_1": 0.0, "mrr": 0.0,
                 "per_question": [{ "question": "...", "rank_of_relevant": null }] },
  "refusal":   { "n_answerable": 25, "n_unanswerable": 15,
                 "correct_refusals": 0, "false_refusals": 0 },
  "grounding": { "n": 40, "top_source_contains_claim_rate": 0.0 },
  "latency_ms":{ "n": 50, "p50": 0, "p95": 0,
                 "breakdown": { "embed": 0, "retrieve": 0, "rerank": 0, "llm": 0 } },
  "cost":      { "llm_calls_per_100_queries": 100, "avg_input_tokens": 0,
                 "avg_output_tokens": 0, "est_usd_per_100_queries": 0.0 },
  "stability": { "repeats": 10, "identical_top_result_rate": 0.0 }
}
```

**Commit the artifacts.** `evals/benchmarks/baseline.json`, `probes-only.json`, `full.json`. A
number in a PR description is an assertion; a committed artifact with a corpus checksum and a git
SHA is evidence, and it is still evidence in six months when someone asks.

### 4B.3 What to measure, and why each one

**Retrieval quality — use MRR as the headline, not relevant@1.**

`relevant@1` is binary per question. At n=15 a single question is 6.7 percentage points, so a
"5% improvement" is 0.75 questions and means nothing. **Mean Reciprocal Rank** gives graded credit
for position (rank 1 → 1.0, rank 2 → 0.5, rank 3 → 0.33), so it moves smoothly, has far lower
variance at small n, and still rewards exactly what re-ranking is supposed to do.

Report `recall@15` alongside it. The two answer different questions and this ticket touches both:

- **recall@15 moves when the index fix lands** — the candidate was never retrieved before (2.2)
- **MRR and relevant@1 move when re-ranking lands** — the candidate was retrieved and mis-ordered

If you only report one number you cannot tell those apart, and the `probes-only` row in 4B.1 is
what separates them.

**Refusal correctness — this needs a negative set that does not exist yet.**

The dataset from 3.3 is all answerable questions. The confidence threshold's entire job is
declining the *un*answerable ones, and nothing currently measures that.

Add ~15 questions the corpus genuinely cannot answer — *"What is the capital of Jupiter?"*,
*"What are Malaysia's student visa requirements?"* (no Malaysian source is configured). Then:

- **correct refusals** — unanswerable questions that were refused
- **false refusals** — answerable questions that were wrongly refused

Both matter, and the second one is the honest counterweight. A threshold set high enough to refuse
everything scores 100% on the first metric. **Report them together or neither.**

**Latency — the re-ranker costs time and the threshold saves it.**

n=50 minimum for a usable p95. Discard the first 3 runs as warm-up: the cross-encoder loads ~90 MB
on first use (2.12) and including that in p50 makes the re-ranker look catastrophic.

Break it down — embed / retrieve / rerank / LLM. The breakdown is what lets you say *"re-ranking
added 45 ms p50 while the threshold removed a 2.4 s LLM call on 18% of queries"*, which is a real
engineering result. A single end-to-end number cannot support that sentence.

**Cost — the threshold's saving is deterministic and therefore the safest number here.**

LLM calls per 100 queries, before and after. If 18% of queries are refused pre-LLM, that is exactly
18% fewer calls — a code-path fact, not a statistical estimate, and it does not need a large n to
be true. Convert to USD at the AgentRouter published rates ($2/$10 per 1M), and **note that
`rag_service.py:274` currently prices at haiku rates** (2.14) so do not source the figure from
there.

**Stability — the crispest before/after in the whole ticket.**

Same query, 10 times, count identical top results. If `ivfflat.probes = 1` is causing 2.2, the
baseline will be visibly non-deterministic and the fix takes it to 100%. That is a large,
deterministic, per-query-verifiable step change — the kind of number that does not need error bars.

### 4B.4 Traps specific to benchmarking

**B1 🔴 The corpus moves under you.** GOA-041 landed re-ingestion at `483d28d`, with weekly and
monthly schedules. If ingestion runs between baseline and after, your delta includes new documents.

**The `corpus_checksum` field exists for exactly this.** The harness must compute it (a hash of the
sorted document IDs) and **refuse to run** if it differs from the baseline artifact's, unless
`--allow-corpus-drift` is passed explicitly. A silent corpus change is a benchmark that measures
ingestion and calls it re-ranking.

Also: disable the ingestion schedules for the duration, or run the whole matrix in one sitting.

**B2 🟠 The cache invalidates the latency comparison.** An "after" measured with a warm cache
against a "before" with no cache is not a comparison of re-ranking — it is a demonstration that
caching works. Run the whole matrix **cache-disabled** for the like-for-like, then measure the
cache separately as its own claim with its own hit rate.

**B3 🟠 The baseline itself is noisy, because of the very bug you are fixing.** `ivfflat.probes = 1`
means the baseline may return different results run to run (6.5). So the baseline needs the same
repeat treatment as everything else — **measure it 3 times and report the spread**, not once. A
baseline captured on a lucky run makes the improvement look smaller; an unlucky one inflates it.

**B4 🟠 LLM-judged metrics are nondeterministic.** Anything graded by a model (grounding,
answer-concept matching) varies between runs even at temperature 0. Either keep LLM-judged metrics
out of the headline claim, or run them 3 times and report the mean with the range. The
retrieval metrics — MRR, recall@15, stability, latency, cost — are all deterministic given a fixed
corpus, which is why they make better CV numbers.

**B5 🟠 n=15 cannot support a 5% claim.** Covered above; the fix is MRR plus a larger set.
**Target ~40 questions total (25 answerable + 15 unanswerable).** That is an afternoon of work and
it is the difference between a number that holds up and one that does not.

**B6 🟡 Machine state drifts.** Interleave the runs — baseline, full, baseline, full — rather than
all-baseline-then-all-full. Note anything else running on the machine. Ollama serving embeddings on
the same box is a real source of variance.

**B7 🟡 Don't benchmark through the Gateway.** Measure RAG directly on `:8084` for the component
numbers — Gateway JWT, rate limiting and SSE framing add variance that has nothing to do with what
you changed. Measure through the Gateway once, separately, for the end-to-end user-facing figure,
and label it as such.

### 4B.5 When to run it

- **After Step 2, before Step 3's harness exists** — capture `baseline` and `probes-only` using the
  raw diagnostic. This is the pair that answers 3.1
- **After Step 3** — re-capture `baseline` properly with the full harness and the real dataset
- **After Step 6** — `width-only`, `rerank`
- **After Step 8** — `full`, plus the separate cache-enabled run

Every capture goes in the PR as a committed artifact, and the matrix table from 4B.1 goes in the PR
description with the real numbers filled in.

### 4B.6 What actually belongs on a CV

Blunt guidance, because the failure mode here is a number that collapses under one follow-up
question.

**Claims that hold up:**
- *"Diagnosed a pgvector ANN recall defect (ivfflat scanning 1% of the corpus at default probes);
  retrieval recall@15 rose from X% to Y% across a 40-question benchmark."* Large effect,
  deterministic, per-query verifiable, and the diagnosis is the interesting part.
- *"Eliminated LLM inference on low-confidence queries, cutting LLM calls per 100 queries from 100
  to N."* A code-path fact.
- *"Cross-encoder re-ranking improved MRR from A to B on a 40-question benchmark (n stated, harness
  committed)."* Defensible *because* you state n and can produce the artifact.

**Claims that will not survive:**
- Any percentage without a denominator.
- *"Improved accuracy by 5%"* on 15 questions — that is 0.75 questions and an interviewer who
  benchmarks things will do that arithmetic in their head.
- Anything measured across two corpus states (B1).
- A latency improvement that was actually the cache (B2).

**And the thing worth leading with is not a number at all.** If Step 1 shows BUG-051 was an index
recall problem rather than the ranking problem the ticket assumed, then the story is: *"the
assigned fix would not have solved the reported bug; I measured first, found the real cause, fixed
it, and then implemented the re-ranker as a separate improvement with its own measured effect."*

That is a senior-engineer story. The benchmark numbers are what make it credible — they are the
evidence, not the headline.

---

## 5. Testing

> [!CAUTION]
> **Skeleton-mentor rule 7 applies: you write these, run them, and iterate to green yourself.** A
> mechanical failure — bad fixture, wrong mock, off-by-one — you fix. A failure that exposes a real
> gap in the owner's logic goes back through rule 4: what is wrong, why it matters, what to watch
> for next time. Do not patch their implementation to make your test pass.

### 5.0 Rewrite the test that asserts the bug

Before writing anything new, `test_query.py:158` (2.8). It asserts a low-similarity query returns
200 with an answer. Replace it with one asserting the refusal contract, and **say in chat that you
changed it and why** — an inherited test going from green to rewritten looks like tampering unless
it is named.

### 5.1 Unit — threshold and refusal

- All chunks below threshold → `answer is None`, `reason == "insufficient_data"`, `suggestion`
  non-empty
- **Zero LLM calls on a refused query.** Assert on a call counter on the LLM client, not on the
  response body. This is the AC's *"threshold check before LLM call"* and the response body cannot
  distinguish "refused before calling" from "called and discarded"
- One chunk at exactly the threshold → boundary behaviour matches the documented comparison
  (`<` vs `<=`) — pick one, document it, test it
- Above threshold → normal answer, LLM called exactly once
- **FAQ hit with a trigram similarity below the vector threshold is still answered** (2.6). Force
  it by lowering `FAQ_SIMILARITY_THRESHOLD` in the test. This is the test that proves the FAQ
  bypass is deliberate rather than coincidental
- Empty corpus → refusal, not a crash and not an empty-context LLM call

### 5.2 Unit — re-ranker

- Reordering: candidates whose cosine order differs from cross-encoder order come back in
  cross-encoder order
- **Every key on every candidate dict survives** — `id`, `source_url`, `similarity`. Assert the
  key set, not just the count
- `top_n` respected; fewer candidates than `top_n` returns what exists without padding
- **Model failure degrades to cosine order, does not raise, and increments the failure counter.**
  Assert all three
- Batched into one `predict()` call — assert the call count is 1 for 15 candidates
- The model is loaded once: two queries do not construct two `CrossEncoder` instances

### 5.3 Unit — citations

- `sources` maps only persisted columns; a row with `title = NULL` yields `title: None`, **not a
  derived or invented string**
- `relevance_score` is on the scale decided in 3.5 — assert the range, so a cross-encoder logit
  leaking into this field fails the test (2.10)
- Ordering after Step 7 is by support score, not cosine
- A refusal still returns populated `sources` (3.4)

### 5.4 Integration — against real dependencies

The ticket's cross-service block requires *"a real database, a real queue, a real HTTP hop. Not
fakes standing in for the thing being tested."*

- Query against the **real** corpus in the **real** Postgres, with the real ivfflat index, and
  assert the returned chunk count and score range. Every existing test in `test_query.py` mocks
  `db.pool` — none of them would notice an index change, and Step 2 is an index change
- Visa citation, per the AC: ingest a visa fixture **through the GOA-108 canonical handler**, then
  query and assert the citation matches the stored official URL. **The test must not insert a
  document row directly** — the AC says so explicitly, and a direct insert would bypass exactly the
  path that populates `title` and `source_url`
- All chunks below threshold, end to end → refusal with `reason`
- **Through the Gateway, not RAG's port**: `POST /api/chat` with a RAG-intent question returns a
  cited answer, and a low-confidence question returns the refusal as a deliberate SSE event rather
  than the string `"None"` (2.7)

### 5.5 Eval

- Baseline recorded **after** Step 2 and **before** Step 6, on the real dataset from 3.3
- relevant@1 and recall@15 both reported. If relevant@1 improved and recall@15 did not, the
  re-ranker did the work; if both moved, Step 2 did some of it and the attribution must say so
- Both paths measured in **one** invocation (Step 3)
- Infrastructure failure exits non-zero with a message distinguishable from a quality regression
- BUG-051 and BUG-052 present as dataset items and passing

### 5.6 End-to-end — the owner runs these, with their own eyes

```bash
cd "D:/ITI/Graduation Project/GOA"
docker compose up -d
```

```bash
# 1. BUG-051, the original failing case
curl -s -X POST http://localhost:8084/query \
  -H "X-Internal-Api-Key: $INTERNAL_API_KEY" -H 'Content-Type: application/json' \
  -d '{"question":"How many questions are in the IELTS Reading test?","userId":"e2e-033"}' | jq
# expect: the 40-questions chunk cited, sources[0] containing the claim
```

```bash
# 2. BUG-052, citation order
curl -s -X POST http://localhost:8084/query \
  -H "X-Internal-Api-Key: $INTERNAL_API_KEY" -H 'Content-Type: application/json' \
  -d '{"question":"What does band 7 mean?","userId":"e2e-033"}' \
  | jq '.sources[] | {title, url: .source_url, relevance_score}'
# then READ sources[0]'s chunk and confirm by eye that it contains the claim
```

```bash
# 3. Refusal, and no LLM call behind it
curl -s -X POST http://localhost:8084/query \
  -H "X-Internal-Api-Key: $INTERNAL_API_KEY" -H 'Content-Type: application/json' \
  -d '{"question":"What is the capital of Jupiter?","userId":"e2e-033"}' | jq
# expect answer:null, reason:"insufficient_data", sources still populated
docker compose logs rag --since 1m | grep -ic "LLM invoke"     # expect 0
```

```bash
# 4. Through the Gateway -- the cohesion requirement
curl -sN -X POST http://localhost:8080/api/chat \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"message":"What is the capital of Jupiter?","sessionId":"e2e-033-1"}'
# expect a deliberate refusal event. NOT the literal string "None" (2.7)
```

```bash
# 5. Cache actually caches
curl -s -o /dev/null -w 'first  %{time_total}s\n' -X POST http://localhost:8084/query ...
curl -s -o /dev/null -w 'second %{time_total}s\n' -X POST http://localhost:8084/query ...
curl -s http://localhost:8084/metrics | grep -E "goa_rag_(cache_hits|requests)_total"
# cache_hits_total must be > 0. Zero means the counter was added and the cache was not (2.9)
```

```bash
# 6. Recall, before and after
docker compose exec -T postgres psql -U goa -d rag_db -c "SHOW ivfflat.probes;"
python evals/rag_retrieval_eval.py --baseline --rerank
```

**Paste the output of all six into the PR.**

---

## 6. The review loop — before anyone says "done"

### 6.1 Does it compile and start?

```bash
cd services/rag && python -m compileall -q app && python -c "import app.main"
docker compose build rag && docker compose up -d rag
docker compose logs rag --since 2m | grep -iE "error|traceback|cross-encoder|redis"
```

The startup log is load-bearing here: 2.9 is a service that logs a cache it does not have. Confirm
the cross-encoder loads **at startup** and appears in the log, and that a missing model cache fails
loudly rather than deferring to the first user query.

### 6.2 Is the threshold really upstream of the LLM?

The single highest-value check in this ticket, because 2.1 is a feature that already exists and
does nothing.

```bash
docker compose exec -T rag grep -n "threshold\|insufficient_data" app/services/rag_service.py app/api/query.py
```

Read the **line numbers**. The check must appear in `rag_service.py` before the prompt is built.
If it is still only in `query.py`, or if it is in both, the fix is not in.

Then prove it behaviourally: fire a refused query and grep the logs for an LLM invocation. **Zero.**
A response with `answer: null` proves nothing on its own — the LLM may have been called and its
output discarded, which costs money and reports as a working feature.

### 6.3 Does the wiring point where the comment says it points?

```bash
grep -rn "0.6" services/rag/app/            # a surviving literal means config was not used
grep -rn "cache_hit=\"false\"" services/rag/app/   # zero, or Step 8 is incomplete
grep -rn "GOA-015" services/rag/app/        # the stale TODO from 2.9
grep -rn "CrossEncoder(" services/rag/app/  # exactly one construction site, at startup
docker compose exec -T rag printenv | grep -iE "threshold|probes|rerank|hf_home|transformers"
```

### 6.4 Trace one real query the whole way

```bash
curl -s -X POST http://localhost:8084/query ... | jq
docker compose logs rag --since 1m | tail -20        # retrieval_score? chunks used? rerank ran?
docker compose exec -T postgres psql -U goa -d rag_db \
  -c "SELECT id, title, left(source_url, 60) FROM documents WHERE id = '<sources[0].id>';"
# then Langfuse: retrieval span shows 15 candidates, generation shows 5. Not 5 and 5.
```

That last check is the one that catches a re-ranker wired in as a no-op: if the retrieval span
shows 5 candidates, retrieval was never widened and the re-ranker is sorting a list that was
already the answer.

### 6.5 Do the same thing twice

```bash
for i in 1 2 3; do curl -s -X POST http://localhost:8084/query ... | jq -c '.sources[0].id'; done
```

**Identical every time.** Non-deterministic top results across identical queries mean `ivfflat`
approximation is still in play (2.2) — which also means every measurement in Step 3 and Step 6 has
noise in it larger than the 5% you are trying to demonstrate.

### 6.6 Break it deliberately

```bash
# a) Re-ranker unavailable -- degrade to cosine, stay up, and SAY SO
docker compose exec -T rag mv /root/.cache/huggingface /root/.cache/hf-disabled
docker compose restart rag
curl -s -X POST http://localhost:8084/query ... | jq '.sources | length'   # still answers
curl -s http://localhost:8084/metrics | grep -i rerank                    # failure counter moved
docker compose exec -T rag mv /root/.cache/hf-disabled /root/.cache/huggingface

# b) Redis down -- cache miss, not a 500
docker compose stop redis-cache && curl -s -X POST http://localhost:8084/query ... | jq '.answer'
docker compose start redis-cache

# c) Empty corpus -- refusal, not an empty-context LLM call
docker compose exec -T postgres psql -U goa -d rag_db -c "BEGIN; DELETE FROM documents; \
  SELECT count(*) FROM documents; ROLLBACK;"
```

Check (a) carefully. A re-ranker that silently falls back is indistinguishable from one that works
— **that is the whole point of the failure counter**, and it is the check that tells you six weeks
from now whether re-ranking has been running at all.

### 6.7 Ask what is still not wired

```bash
grep -rn "relevant_at_1\|recall_at" evals/                 # zero = Step 3 not done
grep -rn "title" services/rag/app/schemas/query.py         # zero = Step 4 not done
grep -rn "reason\|suggestion" services/rag/app/schemas/query.py
grep -rn "answer.*is None\|refusal" services/orchestration/app/services/client.py  # zero = 2.7 open
grep -rn "Dummy RAG question" evals/golden_dataset.json    # still feeding the metric?
ls services/rag/app/migrations/ | tail -3                  # is 027 there, with a rollback?
```

### 6.8 Re-read the tests you inherited

Every test in `test_query.py` mocks `db.pool`. Ask of each: **if the index were misconfigured,
would this test notice?** The answer is no for all of them, and Step 2 is an index change. That gap
is why 5.4's first item exists.

### 6.9 Check nothing else broke

```bash
docker compose exec -T rag python -m pytest -q
docker compose exec -T orchestration python -m pytest -q
docker compose exec -T ingestion python -m pytest -q      # if Step 4 touched ingestion
cd services/gateway && go test -count=1 ./...
python -m pytest evals/tests -q
docker compose config --quiet
```

Orchestration matters specifically: 2.7 changes a contract it consumes. Ingestion matters if 3.2
chose option 1.

---

## 7. Cohesion with other tickets

| Ticket | Relationship |
|---|---|
| **GOA-041** | **Landed at `483d28d`.** It added `DELETE /internal/documents` and re-ingestion. The corpus can change under you — **snapshot `count(*)` and index settings with every measurement**, or Step 6's delta is contaminated by an ingestion run |
| **GOA-108** | Supplies the visa evidence URLs the AC requires citing. 5.4's fixture test must go through its canonical handler |
| **GOA-111** | Structured ingestion. If 3.2 chooses option 1, `title` population lands in its adapters |
| **GOA-027** | **Landed at `3b1d396`.** Langfuse nesting and traceparent are already wired (`372a2a5`), so the retrieval and generation spans in 6.4 are visible without extra work |
| **GOA-034** | OWASP LLM. 2.15's injection surface is its territory — note it, do not solve it |
| **GOA-130** | Cost accounting. 2.14's hardcoded haiku rate belongs to it |
| **GOA-020 / GOA-028** | Own `evals/runner.py`. Step 3 adds a **new** harness rather than editing `run_rag_eval`, so the PR-gating judge accuracy path is untouched. Do not change the shared runner's exit semantics |
| **BUG-051** | May close in **Step 2**, not Step 6. If so, that is a finding worth stating loudly |
| **BUG-052** | Closes in Step 7, and only if citation order is scored on `(answer, chunk)` |

### What must not break

- The FAQ short-circuit's zero-token path. It must not start paying for embedding, retrieval or a
  cross-encoder
- `docker compose` must keep working without AWS
- Orchestration's SSE contract. A refusal is a new event type, not a malformed token
- The `evals/runner.py` PR gate. Step 3 is additive

---

## 8. Definition of done

**Measurement (Step 1–3)**
- [ ] Corpus characterised: row count, category breakdown, similarity distribution
- [ ] The 2.2 diagnostic run; 3.1 answered with evidence, not assumption
- [ ] `0.6` re-derived from the current corpus, or explicitly retained with the measurement shown
- [ ] Real golden dataset with ground-truth chunk IDs, including BUG-051's and BUG-052's queries
- [ ] Baseline relevant@1 and recall@15 recorded **after** any index fix
- [ ] Dummy `"Dummy RAG question N"` rows cannot influence the metric

**Benchmarking (Section 4B)**
- [ ] Every optimisation behind a config flag, so before/after is one binary and one corpus (4B.1)
- [ ] `evals/rag_benchmark.py` emits the full artifact including `fingerprint` (4B.2)
- [ ] `corpus_checksum` computed, and the harness **refuses to run on drift** without an explicit
      override (B1)
- [ ] ~40-question dataset: ~25 answerable + ~15 unanswerable (B5)
- [ ] Whole matrix captured: `baseline`, `probes-only`, `width-only`, `rerank`, `full` (4B.1)
- [ ] All matrix runs **cache-disabled**; the cache measured separately (B2)
- [ ] Baseline captured 3× with the spread reported (B3)
- [ ] Latency n≥50 with warm-up runs discarded, broken down by stage
- [ ] MRR reported as the headline retrieval metric, with recall@15 beside it (4B.3)
- [ ] Correct refusals **and** false refusals reported together
- [ ] Artifacts committed under `evals/benchmarks/`
- [ ] The 4B.1 matrix table appears in the PR description with real numbers

**Retrieval**
- [ ] Index recall settled — `probes`, `lists`, or no ANN index, with the curve behind the number
- [ ] Retrieval width (15) and return width (5) are separate, configurable values
- [ ] `topK` clamped, and its meaning documented
- [ ] Identical queries return identical top results (6.5)

**Threshold**
- [ ] Check is **inside `query_rag`, before the prompt is built** (6.2)
- [ ] **Zero LLM calls on a refused query**, proven from logs
- [ ] Refusal returns `{answer: null, reason, suggestion, sources}` per 3.4
- [ ] FAQ path bypasses it deliberately, with a test that would fail if the bypass were accidental
- [ ] Dead check at `api/query.py:68` removed; counter increments exactly once
- [ ] **Orchestration surfaces the refusal deliberately** (2.7)

**Citations**
- [ ] `{title, url, relevance_score}` from persisted columns only — nothing LLM-generated (2.4)
- [ ] `title` nullable; `None` where unknown; no invented fallback
- [ ] `relevance_score` on the scale decided in 3.5, range-asserted in a test
- [ ] Citation order scored on `(answer, chunk)`; BUG-052's `sources[0]` contains the claim
- [ ] `source_url` truncation checked (Step 4)

**Re-ranking**
- [ ] Model loaded once at startup; one `CrossEncoder(` construction site
- [ ] Baked into the image; missing cache fails at startup, not on first query
- [ ] Batched into one `predict()`
- [ ] Failure degrades to cosine order **and increments a visible counter** (6.6a)
- [ ] relevant@1 improvement reported as measured — **not adjusted to reach 5%**

**Cache and metrics**
- [ ] `goa_rag_cache_hits_total` and `goa_rag_requests_total` exist and both move
- [ ] A real cache, keyed on everything that changes the answer
- [ ] `cache_hit` no longer hardcoded; stale GOA-015 TODO deleted
- [ ] `retrieval_score` is the **mean** over used chunks

**Guard**
- [ ] Context delimited; guard after the context
- [ ] A test presents context lacking the answer and asserts refusal
- [ ] Injection surface noted for GOA-034

**Process (0.1–0.5)**
- [ ] skeleton-mentor invoked; NEW/REPEAT declared per component in chat
- [ ] **Every implementation snippet posted in chat; no implementation file written by Antigravity**
- [ ] One step per message, with a gate between each
- [ ] Tests written and run by Antigravity to green (rule 7); design gaps handed back via rule 4
- [ ] Mastery log entry at the end (rule 5)

**Testing**
- [ ] `test_low_similarity_increments_metrics_counter` rewritten, and the rewrite named in chat
- [ ] 5.1–5.3 unit suites
- [ ] 5.4 integration against the **real** database and index, visa fixture through the GOA-108 handler
- [ ] **All six E2E flows in 5.6 run by the owner, output pasted into the PR**
- [ ] Every check in Section 6, including all three deliberate breaks

**Honest reporting**
- [ ] The PR states whether BUG-051 was a recall or a ranking problem, and which step closed it
- [ ] The PR states the measured relevant@1 delta, whatever it is
- [ ] **The owner ran the whole flow and watched it work.** What they ran, what they saw

> [!WARNING]
> **This ticket already contains a finished feature that does nothing.** The 0.6 threshold is
> written, tested, wired to a Prometheus counter and visible on a dashboard, and it has never
> refused a single answer. A Redis client logs `"Connected to Redis for RAG cache"` next to a
> hardcoded `cache_hit="false"`. Fifty golden-dataset rows say `"Dummy RAG question"`. An
> approximate index scans 1% of the corpus and returns a different answer depending on phrasing.
>
> Every one of those is green right now.
>
> The only acceptable evidence here is a number you measured before and after, a refusal you
> watched happen with no LLM call behind it, and a citation you opened and read.
