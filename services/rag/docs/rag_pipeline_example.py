"""
End-to-End RAG Pipeline Example

This script serves as a standalone, runnable educational example demonstrating
the core phases of a Retrieval-Augmented Generation (RAG) system:
1. Ingesting text documents and storing their vector embeddings in PostgreSQL.
2. Generating a vector embedding for a user query.
3. Querying the database using pgvector's cosine distance operator (<=>).
4. Constructing a prompt with retrieved context and generating an answer via Claude.

Prerequisites:
- A running PostgreSQL database with the pgvector extension enabled.
- OPENAI_API_KEY and ANTHROPIC_API_KEY environment variables.
"""

import os
import asyncio
import asyncpg
from openai import AsyncOpenAI
from anthropic import AsyncAnthropic

# Load environment configuration
DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql://goa:goa_pass@localhost:5432/rag_db"
)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "your-openai-api-key")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "your-anthropic-api-key")

# Initialize API clients
openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)
anthropic_client = AsyncAnthropic(api_key=ANTHROPIC_API_KEY)


async def setup_database(conn):
    """Ensure the pgvector extension and the documents table are created."""
    print("Setting up database extensions and table...")
    await conn.execute("CREATE EXTENSION IF NOT EXISTS vector;")
    await conn.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp";')
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            content TEXT NOT NULL,
            embedding VECTOR(1536),
            source_url VARCHAR(255)
        );
    """)


async def get_embedding(text: str) -> list:
    """Generate a 1536-dimensional vector embedding using OpenAI's model."""
    response = await openai_client.embeddings.create(
        input=[text.replace("\n", " ")], model="text-embedding-3-small"
    )
    return response.data[0].embedding


async def ingest_sample_data(conn):
    """Seed the database with sample document chunks."""
    documents = [
        (
            "German student visa requirements: You must show proof of sufficient financial funds, "
            "typically a blocked account (Sperrkonto) containing at least 11,208 EUR for one year.",
            "https://germany.info/visa-funds",
        ),
        (
            "German universities require proof of health insurance. You can register with a public "
            "provider like TK or AOK, or get equivalent private insurance.",
            "https://germany.info/health-insurance",
        ),
        (
            "For language requirements in Germany: English-taught programs usually require an IELTS "
            "score of 6.5 or TOEFL equivalent. German-taught programs require TestDaF 4 or DSH 2.",
            "https://daad.de/language-requirements",
        ),
    ]

    # Check if we already have seeded data
    count = await conn.fetchval("SELECT COUNT(*) FROM documents;")
    if count > 0:
        print("Database already contains documents. Skipping seeding.")
        return

    print("Embedding and seeding sample documents...")
    for content, source in documents:
        embedding = await get_embedding(content)
        await conn.execute(
            "INSERT INTO documents (content, embedding, source_url) VALUES ($1, $2, $3);",
            content,
            embedding,
            source,
        )
    print("Seeding complete.")


async def retrieve_context(conn, query: str, top_k: int = 2):
    """Query the vector database to find the most relevant chunks using Cosine Distance (<=>)."""
    # 1. Embed query on the fly
    query_vector = await get_embedding(query)

    # 2. Perform Cosine Similarity vector search: similarity = 1 - Cosine Distance
    # pgvector operator <=> computes Cosine Distance
    rows = await conn.fetch(
        """
        SELECT content, source_url, 
               1 - (embedding <=> $1::vector) AS similarity
        FROM documents
        ORDER BY embedding <=> $1::vector
        LIMIT $2
    """,
        query_vector,
        top_k,
    )

    return rows


async def generate_answer(query: str, retrieved_chunks) -> str:
    """Formulate prompt with the context chunks and request response from Anthropic's Claude."""
    context_str = "\n\n".join(
        [
            f"Source: {row['source_url']}\nContent: {row['content']}"
            for row in retrieved_chunks
        ]
    )

    prompt = f"""You are a helpful assistant. Use the following context to answer the user's question. 
If the answer cannot be found in the context, say that you do not know.

Context:
{context_str}

Question:
{query}

Answer:"""

    print("Sending prompt to Claude...")
    response = await anthropic_client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text


async def main():
    # 1. Connect to PostgreSQL
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        # 2. Setup schema & seed sample data
        await setup_database(conn)
        await ingest_sample_data(conn)

        # 3. Define user question
        question = (
            "What amount of money do I need to show for a student visa in Germany?"
        )
        print(f"\nUser Question: '{question}'")

        # 4. Retrieval Phase
        print("Retrieving relevant context from database...")
        chunks = await retrieve_context(conn, question, top_k=2)
        print(f"Retrieved {len(chunks)} relevant chunks:")
        for idx, chunk in enumerate(chunks, 1):
            print(
                f"  [{idx}] Similarity: {chunk['similarity']:.4f} | Source: {chunk['source_url']}"
            )

        # 5. Generation Phase
        answer = await generate_answer(question, chunks)
        print(f"\nClaude's Answer:\n{answer}\n")

    finally:
        await conn.close()


if __name__ == "__main__":
    # To run this script, ensure you have set environment variables:
    # export DATABASE_URL="postgresql://goa:goa_pass@localhost:5432/rag_db"
    # export OPENAI_API_KEY="sk-..."
    # export ANTHROPIC_API_KEY="sk-ant-..."
    # python services/rag/docs/rag_pipeline_example.py
    asyncio.run(main())
