-- The undergraduate field and intended Master's field are separate facts.
-- Older events only carried field_of_study, so backfill it as the intended
-- field until the user explicitly saves a target.
ALTER TABLE local_user_profiles
    ADD COLUMN IF NOT EXISTS target_field_of_study VARCHAR(255) NULL;

UPDATE local_user_profiles
SET target_field_of_study = field_of_study
WHERE target_field_of_study IS NULL;
