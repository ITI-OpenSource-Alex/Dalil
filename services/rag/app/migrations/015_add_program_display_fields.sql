-- GOA-114: program_requirements gains display fields for /match opportunity cards
-- (programName, deadline). GOA-019's OpportunityCard renders these; before this
-- migration /match selected columns that did not exist and returned a 500.

ALTER TABLE program_requirements
ADD COLUMN IF NOT EXISTS program_name VARCHAR(255) NULL,
ADD COLUMN IF NOT EXISTS deadline DATE NULL;

-- Backfill the three seed programs from 008_update_program_requirements.sql
UPDATE program_requirements
SET program_name = 'MSc Computer Science', deadline = '2024-05-31'
WHERE id = '11111111-1111-1111-1111-111111111111';

UPDATE program_requirements
SET program_name = 'BSc Software Engineering', deadline = '2024-06-15'
WHERE id = '22222222-2222-2222-2222-222222222222';

UPDATE program_requirements
SET program_name = 'MA Data Science', deadline = '2024-07-01'
WHERE id = '33333333-3333-3333-3333-333333333333';

-- Down migration (documented, NOT executed):
-- This service's migration runner (app/core/database.py) executes each .sql file in
-- full, with no up/down markers — leaving the DROP inline would add the columns and
-- then immediately drop them again. Kept here as the documented rollback per GOA-079.
--
-- ALTER TABLE program_requirements
-- DROP COLUMN program_name,
-- DROP COLUMN deadline;
