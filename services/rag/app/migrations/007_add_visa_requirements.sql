CREATE TABLE IF NOT EXISTS visa_requirements (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    country VARCHAR(100) NOT NULL,
    visa_type VARCHAR(100) NOT NULL,
    issuing_body VARCHAR(255) NOT NULL,
    requirements JSONB NOT NULL,
    proof_of_funds JSONB NULL,
    source_url VARCHAR(255) NULL,
    processing_days_min INTEGER NULL,
    processing_days_max INTEGER NULL,
    notes TEXT NULL,
    content_hash VARCHAR(64) NULL,
    last_scraped_at TIMESTAMP NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    CONSTRAINT uq_visa_requirements UNIQUE (country, visa_type, issuing_body)
);