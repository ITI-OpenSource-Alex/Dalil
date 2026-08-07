-- GOA-032 / BUG-040: a session's overall band is now absent, not zero, when
-- fewer than 3 of the 4 IELTS criteria completed.
--
-- The column was NOT NULL, so the only way to persist such a session was to
-- write 0.0 -- indistinguishable from a genuine band of zero, and rendered in
-- session history as "Band 0.0" for an evaluation that never produced a band.
-- That is the same defect class as BUG-055 (a missing score reported as a real
-- one), one layer further out.
--
-- Existing rows are left alone: they were all written by the pre-streaming code
-- path, which only ever persisted a computed average, so none of them are
-- placeholder zeros that need rewriting.
ALTER TABLE speaking_sessions
    ALTER COLUMN overall_band DROP NOT NULL;
