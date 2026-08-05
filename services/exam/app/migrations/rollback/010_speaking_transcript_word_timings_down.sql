-- GOA-133 rollback. Dropping these discards the acoustic evidence for every
-- session recorded since the migration; the transcripts themselves are untouched.
ALTER TABLE exam_speaking_transcripts DROP COLUMN IF EXISTS words;
ALTER TABLE exam_speaking_transcripts DROP COLUMN IF EXISTS audio_duration_s;
