# RAG Service

The RAG (Retrieval-Augmented Generation) service is a FastAPI application that processes natural language queries about university scholarship opportunities, searches a PostgreSQL database using `pgvector` cosine similarity, and synthesizes answers using Claude (Anthropic).

---

## What it Owns

* **Responsibility**: Vector similarity document search, context retrieval, LLM answer synthesis, and storage of visa stubs.
* **Database**: PostgreSQL (`rag_db`) with the `vector` extension enabled. Manages `documents` and `program_requirements` tables.
* **Queues**: N/A (Receives upsert requests synchronously from the Ingestion Worker).

---

## API Reference

### 1. `POST /query`
* **Request Shape**:
```json
{
  "question": "Are there scholarships for mechanical engineering?",
  "userId": "usr_abc123",
  "topK": 5
}
```
* **Response Shape (200 OK)**:
```json
{
  "answer": "Yes, there is the DAAD Scholarship for engineering students...",
  "chunks": [
    {
      "id": "doc_uuid_1",
      "content": "DAAD offers full engineering scholarships...",
      "score": 0.89
    }
  ]
}
```
* **Error Codes**:
  * `422 Unprocessable Entity`: Body validation failed.
  * `500 Internal Server Error`: LLM / Embedding call failure.

### 2. `POST /internal/documents`
* **Auth Required**: Yes (`X-Internal-Api-Key` header)
* **Request Shape**:
```json
{
  "documents": [
    {
      "content": "Scholarship info text...",
      "embedding": [0.012, -0.043, "... 1536 float values"],
      "source_url": "https://uni.de",
      "category": "engineering"
    }
  ]
}
```
* **Response Shape (200 OK)**: `{"status": "success", "upserted": 1}`

### 3. `POST /internal/visa-requirements`
* **Auth Required**: Yes (`X-Internal-Api-Key` header)
* **Request Shape**:
```json
{
  "country": "Germany",
  "visa_type": "Student",
  "issuing_body": "Embassy",
  "requirements": {"blocked_account": true}
}
```
* **Response Shape (200 OK - Stub)**:
```json
{
  "status": "success",
  "message": "Stub processed successfully"
}
```

---

## Environment Variables

| Variable Name | Description | Default Value |
| :--- | :--- | :--- |
| `PORT` | FastAPI server port binding. | `8084` |
| `DATABASE_URL` | PostgreSQL connection URL. | `postgresql://goa:goa_pass@postgres:5432/rag_db` |
| `OPENAI_API_KEY` | OpenAI API key used to embed incoming user queries. | `mock-key` |
| `ANTHROPIC_API_KEY` | Anthropic API key used to synthesize RAG answers. | `mock-key` |
| `INTERNAL_API_KEY` | Internal token used to authorize ingestion uploads. | `supersecret_internal_key_123` |

---

## How to Run Locally

### Running outside Docker
```bash
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8084 --reload
```

### Running with Docker
```bash
docker compose up -d rag
```

---

## How to Run Tests

```bash
# Run pytest suite inside the container
docker compose exec rag pytest
```
