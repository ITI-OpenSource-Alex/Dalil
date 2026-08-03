DROP INDEX IF EXISTS documents_embedding_idx ;

ALTER TABLE documents ALTER COLUMN embedding TYPE vector(1536) USING embedding::vector(1536);

CREATE INDEX IF NOT EXISTS documents_embedding_idx ON documents USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

