CREATE TABLE IF NOT EXISTS crawl_cursors (
    source_name VARCHAR(100) NOT NULL,
    discipline VARCHAR(100) NOT NULL,
    last_page INTEGER DEFAULT 1,
    next_cursor INTEGER DEFAULT 0,
    scroll_offset INTEGER DEFAULT 0,
    total_items INTEGER,
    exhausted BOOLEAN DEFAULT FALSE,
    completion_status VARCHAR(30) DEFAULT 'pending',
    last_attempt_at TIMESTAMPTZ,
    last_success_at TIMESTAMPTZ,
    failure_count INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (source_name, discipline)
);

CREATE TABLE IF NOT EXISTS crawl_urls (
    url_hash VARCHAR(64) PRIMARY KEY,
    source_name VARCHAR(100) NOT NULL,
    discipline VARCHAR(100) NOT NULL,
    url TEXT NOT NULL,
    status VARCHAR(30) NOT NULL,
    page_status VARCHAR(30) NULL,
    attempts INTEGER DEFAULT 0,
    failure_count INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    last_attempt_at TIMESTAMPTZ,
    last_success_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS crawl_sources (
    source_name VARCHAR(100) NOT NULL,
    source_key TEXT NOT NULL,
    source_url TEXT,
    completion_status VARCHAR(30) DEFAULT 'pending',
    last_attempt_at TIMESTAMPTZ,
    last_success_at TIMESTAMPTZ,
    failure_count INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (source_name, source_key)
);

CREATE TABLE IF NOT EXISTS ingestion_runs (
    run_id UUID PRIMARY KEY,
    started_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TIMESTAMPTZ,
    completion_status VARCHAR(30) NOT NULL DEFAULT 'running',
    remaining INTEGER NOT NULL DEFAULT 0,
    error_message TEXT
);

ALTER TABLE crawl_urls ADD COLUMN IF NOT EXISTS page_status VARCHAR(30) NULL;
ALTER TABLE crawl_urls ADD COLUMN IF NOT EXISTS failure_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE crawl_urls ADD COLUMN IF NOT EXISTS last_attempt_at TIMESTAMPTZ;
ALTER TABLE crawl_urls ADD COLUMN IF NOT EXISTS last_success_at TIMESTAMPTZ;
ALTER TABLE crawl_cursors ADD COLUMN IF NOT EXISTS next_cursor INTEGER DEFAULT 0;
ALTER TABLE crawl_cursors ADD COLUMN IF NOT EXISTS total_items INTEGER;
ALTER TABLE crawl_cursors ADD COLUMN IF NOT EXISTS completion_status VARCHAR(30) DEFAULT 'pending';
ALTER TABLE crawl_cursors ADD COLUMN IF NOT EXISTS last_attempt_at TIMESTAMPTZ;
ALTER TABLE crawl_cursors ADD COLUMN IF NOT EXISTS last_success_at TIMESTAMPTZ;
ALTER TABLE crawl_cursors ADD COLUMN IF NOT EXISTS failure_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE crawl_cursors ADD COLUMN IF NOT EXISTS error_message TEXT;
