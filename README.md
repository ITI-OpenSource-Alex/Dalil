# GOA Platform

A multi-service backend architecture.

## Quick Start (Local Development)

This project uses Docker Compose to run all services locally.

1. **Clone the repository:**

   ```bash
   git clone https://github.com/ITI-OpenSource-Alex/GOA.git
   cd GOA
   ```

2. **Set up environment variables:**

   ```bash
   cp .env.example .env
   cp services/gateway/.env.example services/gateway/.env
   ```

   Add real provider keys to the root `.env` before running live AI evaluations.

3. **Pull the embedding model:**

   RAG embeds every query through an Ollama server on the **host** (the
   services reach it at `host.docker.internal:11434`; it is deliberately not a
   compose service). The model is not pulled automatically:

   ```bash
   ollama pull nomic-embed-text
   ```

   Skipping this does not fail loudly at startup. Ollama answers with a 404
   (`model "nomic-embed-text" not found`) only when the first query arrives,
   `POST /query` turns that into a 500, orchestration falls back, and the chat
   shows the generic "something went wrong" reply — with the real cause visible
   only in `docker logs goa-rag-1`. Verify with `ollama list` before debugging
   chat.

   `nomic-embed-text` specifically: `EMBEDDING_DIMENSIONS` defaults to 768 and
   must match the pgvector column. Substituting a different-width model (e.g.
   `all-minilm`, 384) fails at insert/query time rather than falling back.

4. **Start the infrastructure:**
   ```bash
   make up
   ```

_(Note for Windows users: The Makefile automatically handles MSYS path conversion for Docker volume mounts)._

5. **Start the frontend:**

   The Next.js app is **not** part of the compose stack — it runs from the host,
   so whatever is checked out in the working tree is what gets served:

   ```bash
   cd services/frontend && npm install && npm run dev
   ```

   It expects the Gateway at `NEXT_PUBLIC_API_URL` (default
   `http://localhost:8080`). If the UI is missing pages you expect, confirm the
   branch you have checked out actually contains them before suspecting a cache
   — `next dev` compiles from the working tree, not from a build artefact.

6. **Verify:**

- Gateway Health: `curl http://localhost:8080/health`
- Frontend: `http://localhost:3000`
- Grafana: `http://localhost:3001` (admin/admin)
