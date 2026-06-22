CREATE TABLE IF NOT EXISTS documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    content TEXT NOT NULL,
    embedding VECTOR(1536),
    source_url VARCHAR(255),
    category VARCHAR(100),
    last_updated TIMESTAMP DEFAULT NOW()
);