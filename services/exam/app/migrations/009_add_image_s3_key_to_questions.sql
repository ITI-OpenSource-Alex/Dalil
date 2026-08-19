-- Migration 009: Add nullable image_s3_key to questions
--
-- Academic Writing Task 1 asks the candidate to describe a visual stimulus
-- (a chart, graph, map or diagram), but the questions table had nowhere to
-- record which image belongs to a test, so the prompt was served without the
-- one thing it is about. This adds the S3 object key for that image.
--
-- Nullable on purpose: General Training Task 1 (a letter) and every
-- Reading/Listening/Speaking question carries no stimulus image, so those rows
-- stay NULL and are completely unaffected. Only Academic Writing Task 1
-- questions populate it.
--
-- IF NOT EXISTS keeps this idempotent, matching how the runner (see
-- app/core/database.py) applies each file exactly once but tolerates re-runs.

ALTER TABLE questions
    ADD COLUMN IF NOT EXISTS image_s3_key TEXT;
