CREATE TABLE IF NOT EXISTS scholarship_programs (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name                  VARCHAR(255) NOT NULL,
    provider              VARCHAR(255) NOT NULL,
    country               VARCHAR(100) NULL,
    degree_level          VARCHAR(100) NULL,
    award_amount          VARCHAR(255) NULL,
    deadline              DATE NULL,
    eligibility           JSONB NOT NULL DEFAULT '{}',
    citizenship_eligible  BOOLEAN DEFAULT TRUE,
    min_gpa               DECIMAL(4,2) NULL,
    min_ielts             DECIMAL(3,1) NULL,
    source_url            VARCHAR(500) NOT NULL,
    content_hash          VARCHAR(64) NOT NULL,
    last_scraped_at       TIMESTAMP DEFAULT NOW(),
    updated_at            TIMESTAMP DEFAULT NOW(),
    CONSTRAINT uq_scholarship_programs UNIQUE (provider, name)
);
