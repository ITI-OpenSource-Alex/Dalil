-- GOA-088: program_requirements needs the same upsert/idempotency support that
-- visa_requirements already has (content_hash, source_url, last_scraped_at) plus a
-- unique key to upsert on, none of which existed on this table before this migration.
ALTER TABLE program_requirements ADD COLUMN content_hash VARCHAR(64) NULL;
ALTER TABLE program_requirements ADD COLUMN source_url VARCHAR(500) NULL;
ALTER TABLE program_requirements ADD COLUMN last_scraped_at TIMESTAMP DEFAULT NOW();
ALTER TABLE program_requirements ADD COLUMN updated_at TIMESTAMP DEFAULT NOW();

ALTER TABLE program_requirements
    ADD CONSTRAINT uq_program_requirements UNIQUE (university, degree_level, country);
