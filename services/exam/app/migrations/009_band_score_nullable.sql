-- GOA-134: exam_results.band_score becomes nullable.
--
-- The column was DECIMAL(3,1) NOT NULL, so "the swarm could not score this
-- session" had no representation and the caller was forced to invent a number.
-- It invented 0.0 -- a band the model never produced, persisted as the
-- candidate's official IELTS speaking score and indistinguishable from a genuine
-- zero for anyone reading the table later.
--
-- This mirrors services/speaking/migrations/003_overall_band_nullable.sql, which
-- made exactly this change to speaking_sessions.overall_band under GOA-032 for
-- exactly this reason. The exam service persists the same value and never got
-- the same treatment.
--
-- Existing 0.0 rows are NOT rewritten. Some of them are fabricated bands and
-- some may be legitimate, and this migration cannot tell them apart. The
-- decision on those rows belongs to whoever inspects them -- see the DoD item on
-- identifying already-orphaned sessions.

ALTER TABLE exam_results ALTER COLUMN band_score DROP NOT NULL;
