-- GOA-137: keep the full-text representation inseparable from document content.
-- A generated column cannot miss a backfill or drift after an update.
ALTER TABLE documents
    ADD COLUMN IF NOT EXISTS content_tsv tsvector
    GENERATED ALWAYS AS (
        to_tsvector(
            'english',
            coalesce(title, '') || ' ' || coalesce(content, '')
        )
    ) STORED;

CREATE INDEX IF NOT EXISTS documents_content_tsv_idx
    ON documents USING GIN (content_tsv);
