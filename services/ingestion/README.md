# Ingestion Service

The Ingestion service is a background worker (compatible with AWS Lambda or standalone Python scripts) that processes document parsing pipelines. It scrapes university requirement pages using custom adapters, splits text into token-bounded overlaps, batches embedding calls to OpenAI, and upserts results into the RAG Service.

---

## What it Owns

* **Responsibility**: Web scraping, token-based text splitting, batch OpenAI embeddings retrieval, and RAG database populating.
* **Database**: N/A.
* **Queues**: Subscribes to the `ingestion-queue` SQS queue.

---

## Processing Details & Algorithms

### 1. Source Adapters
* **`SourceAdapter`**: Abstract base class defining the `scrape(url: str) -> list[Document]` contract.
* **`TestFixtureAdapter`**: Development adapter returning 10 hardcoded mock university pages.

### 2. Token-Based Chunking
* Uses the **`cl100k_base`** tokenizer (OpenAI `tiktoken`).
* **Chunk size**: Max 500 tokens.
* **Chunk overlap**: 50 tokens.
* **Deterministic ID**: Generates UUID v5 hashes using the text content and a fixed namespaces constant (`INGESTION_NAMESPACE`) to prevent duplicate indexing across runs.

### 3. Batching & Uploads
* Batches embedding generations in groups of 100 to maximize throughput.
* Performs a similarity check first; if the hash matches, it bypasses the OpenAI API call (zero embedding cost for duplicate runs).
* Syncs with the RAG Service using `POST /internal/documents` with the `X-Internal-Api-Key` authorization header.

---

## Environment Variables

| Variable Name | Description | Default Value |
| :--- | :--- | :--- |
| `RAG_SERVICE_URL` | Endpoint URL of the target RAG service. | `http://rag:8084` |
| `OPENAI_API_KEY` | OpenAI credential used to compute 1536-dimensional embeddings. | `mock-key` |
| `INTERNAL_API_KEY` | Shared secret key for RAG service internal upload authentication. | `supersecret_internal_key_123` |
| `DRY_RUN` | If set to `true`, outputs the chunks to the console without hitting OpenAI or writing to RAG. | `false` |

---

## How to Run Locally

### Running outside Docker
```bash
pip install -r requirements.txt
# Run the pipeline handler directly
PYTHONPATH=. python services/ingestion/handler.py
```

### Running with Docker
```bash
docker compose run --rm ingestion python handler.py
```

---

## How to Run Tests

```bash
pytest
```
