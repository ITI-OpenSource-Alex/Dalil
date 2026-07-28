-- Allow 'abandoned' as a session status.
--
-- Migration 006 added last_heartbeat_at but left the CHECK constraint from 001
-- untouched, so sweep_abandoned()'s `SET status = 'abandoned'` violated it on
-- every run. run_sweep_loop catches Exception and logs sweep_error, so the
-- sweep failed silently every 300 seconds since it was merged, and no session
-- could ever be marked abandoned (BUG-053).
--
-- Read 007 and 008 together. On its own this migration is actively harmful: it
-- is what makes the sweep's write succeed, and until the threshold accounts for
-- exam length a candidate sitting a 60-minute reading exam would be marked
-- abandoned at minute 10 and get 403 on submit, losing the attempt (BUG-054).
-- They are safe today only because this constraint rejects the write.

ALTER TABLE exam_sessions
    DROP CONSTRAINT IF EXISTS exam_sessions_status_check;

ALTER TABLE exam_sessions
    ADD CONSTRAINT exam_sessions_status_check
    CHECK (status IN ('pending', 'in_progress', 'submitted', 'scored', 'abandoned'));
