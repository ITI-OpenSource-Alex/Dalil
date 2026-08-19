ALTER TABLE essays
    ADD COLUMN IF NOT EXISTS task_number INTEGER;

ALTER TABLE essays
    DROP CONSTRAINT IF EXISTS essays_task_number_check;

ALTER TABLE essays
    ADD CONSTRAINT essays_task_number_check
    CHECK (task_number IS NULL OR task_number IN (1, 2));
