-- Migration 005: Add UNIQUE constraint on (book_ref, test_number, skill_area)
--
-- The application already enforces idempotency via get_by_unique_key() before
-- INSERT, but there is no database-level guarantee.  This constraint prevents
-- duplicates under concurrent writes and backs the ON CONFLICT clause used by
-- the batch ingestion pipeline.
--
-- Safe to apply on existing data: the application logic has always prevented
-- duplicates, so no conflicting rows should exist.

ALTER TABLE questions
    DROP CONSTRAINT IF EXISTS uq_questions_book_test_skill;

ALTER TABLE questions
    ADD CONSTRAINT uq_questions_book_test_skill
    UNIQUE (book_ref, test_number, skill_area);
