-- Supports the GET /essays history list (Writing History): a generated
-- overall_band column so a future query can sort/filter by band without a
-- JSONB extraction on every row, and an index on (user_id, uploaded_at DESC)
-- for the list's default "most recent first" ordering.
--
-- overall_band is intentionally not mapped in app/models.py yet -- see the
-- comment on Essay in that file. GET /essays currently extracts overall_band
-- from evaluation_result in Python; this column exists for future direct-SQL
-- sorting/filtering (and for the eventual trend chart) without requiring
-- another migration when that lands.
ALTER TABLE essays
    ADD COLUMN IF NOT EXISTS overall_band NUMERIC(2,1)
    GENERATED ALWAYS AS ((evaluation_result->>'overall_band')::numeric) STORED;

CREATE INDEX IF NOT EXISTS ix_essays_user_id_uploaded_at
    ON essays (user_id, uploaded_at DESC);
