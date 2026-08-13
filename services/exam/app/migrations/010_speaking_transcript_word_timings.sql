-- GOA-133: store the word timings alongside each part's transcript.
--
-- Two of the four IELTS speaking criteria are defined over acoustics -- Fluency
-- and Coherence over speech rate and pausing, Pronunciation over intelligibility
-- -- and neither is recoverable from text. The speech sidecar now returns
-- per-word timings and recognition confidence, and the speaking service derives
-- features from them on the practice path.
--
-- The exam path could not: this table stored transcript_text and an integer
-- duration_s and nothing else, so services/exam had nothing to forward to the
-- holistic evaluator and those two agents were scored without the evidence they
-- are supposed to use.
--
-- JSONB rather than a child table: the array is written once per part, read once
-- per evaluation, and never queried by its contents. A words table would add a
-- join and a migration for no access-pattern benefit.
ALTER TABLE exam_speaking_transcripts
    ADD COLUMN IF NOT EXISTS words JSONB;

-- duration_s is INTEGER, which is fine for a session clock and lossy for a
-- ratio: a 20.4s part and a 20.6s part both store 20, and words-per-minute
-- computed against that is off by up to 2.5%. The float column carries the
-- sidecar's own figure; duration_s is left alone so nothing that reads it today
-- has to change.
ALTER TABLE exam_speaking_transcripts
    ADD COLUMN IF NOT EXISTS audio_duration_s DOUBLE PRECISION;
