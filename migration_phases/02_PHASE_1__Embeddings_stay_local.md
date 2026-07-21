# PHASE 1 — Embeddings stay local

## GOA-118 — Ollama embeddings + pgvector re-dimension

| | |
|---|---|
| **Service** RAG + Ingestion | **Priority** P1 | **Points** 2 | **Dependencies** GOA-117 |

> [!IMPORTANT]
> **This ticket survives the router change unchanged.** AgentRouter has **no embeddings model** — all five offerings are chat models. Embeddings must run locally, so the `VECTOR(1536)` → `VECTOR(768)` migration still happens.
>
> **It is time-sensitive:** nothing has ever been embedded (there was never an OpenAI key — see blocker **S4**), so re-dimensioning is free *now* and becomes a full re-embed the moment any ingestion runs. **Do this before Phase 2.**

### Step 1 — Install Ollama and pull the model

Natively on Windows — no Docker GPU passthrough needed.

```bash
ollama pull nomic-embed-text     # 274 MB, 768 dimensions
```

This is the **only** local model now. The 4 GB VRAM constraint that dominated the old plan is irrelevant for a single 274 MB embedder.

### Step 2 — Write migration `017_reembed_dimensions.sql`

First confirm the actual index name — if it is not `documents_embedding_idx`, the `DROP INDEX IF EXISTS` silently no-ops and the `ALTER` then fails:

```bash
docker exec -i $(docker compose ps -q postgres) psql -U goa -d rag_db -c "\d documents"
```

Then confirm nothing has been embedded, because the migration below **discards existing vectors**:

```bash
docker exec -i $(docker compose ps -q postgres) psql -U goa -d rag_db \
  -c "SELECT count(*) FROM documents WHERE embedding IS NOT NULL;"
```
If this returns anything other than `0`, **stop** — you need a re-embed strategy, not a discard.

Create `services/rag/app/migrations/017_reembed_dimensions.sql`:

```sql
-- The ivfflat index is dimension-bound; it must be dropped before the type change.
DROP INDEX IF EXISTS documents_embedding_idx;

ALTER TABLE documents
ALTER COLUMN embedding TYPE vector(768) USING NULL;

CREATE INDEX documents_embedding_idx
ON documents USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);
```

> [!CAUTION]
> **The rollback file goes in `services/rag/app/migrations/rollback/017_reembed_dimensions_down.sql` — NOT beside the migration.**
> The runner globs `migrations/*.sql` and executes everything it finds in sorted order. This is exactly how GOA-116's migration self-destructed: the runner created the table, then immediately ran the adjacent down-migration and dropped it, logging both as applied. Unrecoverable by restart.

### Step 3 — Repoint RAG embeddings

`services/rag/app/services/rag_service.py:28–30`. Ollama exposes an **OpenAI-compatible** embeddings API, so `langchain_openai` stays and no dependency changes:

```python
embeddings_model = OpenAIEmbeddings(
    model=settings.embedding_model,
    openai_api_key=settings.embedding_api_key,   # Ollama ignores it; the SDK requires non-empty
    base_url=settings.embedding_base_url,
    check_embedding_ctx_length=False,            # Ollama has no tokenizer introspection endpoint
)
```

`check_embedding_ctx_length=False` is not optional — without it `langchain_openai` tries to tokenize against an OpenAI tokenizer that does not know this model.

Update the docstring at `rag_service.py:36`, which currently says **"1536-dimensional"**.

Add to `services/rag/app/core/config.py` (the `Settings` class at line 5, which currently declares `openai_api_key: str` and `anthropic_api_key: str` as **required**):

```python
    embedding_base_url: str = "http://host.docker.internal:11434/v1"
    embedding_model: str = "nomic-embed-text"
    embedding_api_key: str = "ollama"
```

`host.docker.internal` is how a container reaches Ollama running natively on the Windows host. On Linux this needs `extra_hosts: ["host.docker.internal:host-gateway"]` in compose.

**Remove the now-unused required `openai_api_key: str`** — and with it the hardcoded key at `docker-compose.yml:83` (defect **D1**).

### Step 4 — Repoint ingestion embeddings

`services/ingestion/embedder.py`:
- `:7–9` `get_openai_client()` → `OpenAI(api_key=settings.embedding_api_key, base_url=settings.embedding_base_url)`
- `:28` `model = "text-embedding-3-small"` → `model = settings.embedding_model`
- `:13` the docstring names the old model — update it.
- `:34` the error log says `"OpenAI embeddings generation failed"` — reword; it will now be misleading.

Batching at `:21` (`batch_size = 100`) is an OpenAI rate-limit optimization. Ollama has no such limit but also no harm from it — leave it.

### Step 5 — Add settings in *both* places

Add the three embedding settings to `docker-compose.yml` **and** to the test `conftest.py` files. **This project has broken twice from adding a setting in only one place** (exam's missing `WRITING_SERVICE_URL`, exam's missing `SPEAKING_SERVICE_URL`).

### Automated tests (ag writes and runs these)

1. `test_embedding_dimension_is_768` — call `generate_embedding("test")`, assert `len(...) == 768`. Integration test; mark it so CI can skip if Ollama is absent, but **it must actually run locally**.
2. `test_embeddings_client_targets_configured_base_url` — assert the client points at `settings.embedding_base_url`, not `api.openai.com`.
3. `test_no_openai_model_names_remain` — assert `text-embedding-3-small` appears nowhere in `services/rag/` or `services/ingestion/`.
4. `test_migration_017_is_idempotent` — apply twice, assert no error and exactly one `migrations_log` row.
5. `test_rollback_not_in_migrations_glob` — assert the `migrations/*.sql` glob does **not** match anything under `rollback/`. Regression guard for the GOA-116 self-destruction.
6. Existing RAG suite green.

### Manual verification (I run this)

**1. Ollama is alive and the model is present:**
```bash
ollama list | grep nomic-embed-text
```
**Expect:** one line naming `nomic-embed-text` at roughly 274 MB.

**2. The migration applied and stayed applied across a restart:**
```bash
docker compose restart rag && sleep 15
docker exec -i $(docker compose ps -q postgres) psql -U goa -d rag_db \
  -c "SELECT migration_file FROM migrations_log WHERE migration_file LIKE '017%';"
```
**Expect:** exactly one row, `017_reembed_dimensions.sql`. **Zero rows means it never ran; two rows means the ledger is broken.**

**3. The column is genuinely 768-dimensional:**
```bash
docker exec -i $(docker compose ps -q postgres) psql -U goa -d rag_db \
  -c "SELECT atttypmod FROM pg_attribute WHERE attrelid='documents'::regclass AND attname='embedding';"
```
**Expect:** `768` (pgvector stores the dimension in `atttypmod` directly). If it says `1536`, the ALTER did not take.

**4. The service produces a real 768-dim vector:**
```bash
docker compose exec rag python -c "
import asyncio
from app.services.rag_service import generate_embedding
v = asyncio.run(generate_embedding('student visa requirements'))
print('dims:', len(v)); print('first3:', [round(x,4) for x in v[:3]])
assert len(v) == 768, f'GOT {len(v)}'
print('PASS')
"
```
**Expect:** `dims: 768`, three plausible floats (**not** all zeros), then `PASS`.

**5. The RAG container did not crash-loop:**
```bash
docker compose ps rag
```
**Expect:** `Up`, **not** `Restarting`. This project has had three separate migration-induced crash-loops; check it every time.

### Definition of Done
- Migration applies and **stays** applied across a restart (`migrations_log` row present, `atttypmod` is 768).
- `generate_embedding()` returns 768 floats.
- Ingestion writes 768-dim embeddings.
- `POST /query` returns a grounded answer with sources.
- No `text-embedding-3-small` and no hardcoded OpenAI key remain anywhere.

---

