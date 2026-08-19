-- Motivation letter review, scored per programme.
--
-- Deliberately NOT stored in `essays`. An essay row carries IELTS submission_type,
-- exam_session_id, task_number and an evaluation_result shaped around the four
-- IELTS band criteria. A motivation letter shares none of that: it is scored 1-5
-- against admissions criteria, not banded 0-9 against language descriptors, and it
-- belongs to a programme rather than an exam session. Overloading `essays` would
-- have meant nullable exam columns on every letter and a polymorphic
-- evaluation_result that neither consumer could type.
CREATE TABLE IF NOT EXISTS motivation_letters (
    id                 SERIAL PRIMARY KEY,
    user_id            VARCHAR(128) NOT NULL,
    -- Nullable on purpose: a student can draft before choosing a programme, and the
    -- review still runs -- programme_fit simply abstains. See criteria.status.
    program_id         VARCHAR(64),
    content            TEXT NOT NULL,
    content_hash       VARCHAR(64) NOT NULL,
    status             VARCHAR(32) NOT NULL DEFAULT 'pending',
    -- NULL until at least three criteria complete. Never 0: "we could not score
    -- this" and "this scored zero" must stay distinguishable, same rule as
    -- cv_reviews.structured_data and the nullable speaking bands.
    overall_score      NUMERIC(3,1),
    criteria           JSONB,
    -- What the programme looked like when the review ran. A review is only
    -- interpretable against the requirements it was written against, and the
    -- catalogue is re-scraped underneath us.
    programme_snapshot JSONB,
    error_message      TEXT,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at       TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_motivation_letters_user_program
    ON motivation_letters (user_id, program_id);

-- Re-submitting identical text for the same programme returns the existing review
-- instead of paying for five more model calls.
--
-- PARTIAL, on completed rows only. A plain unique index looked equivalent and was
-- not: a request that timed out client-side still leaves a 'processing' row behind,
-- and that row then blocked every retry of the same letter with a 500 for the rest
-- of time. Only a finished review is a cache hit worth protecting; anything else
-- must stay re-submittable.
CREATE UNIQUE INDEX IF NOT EXISTS idx_motivation_letters_dedupe
    ON motivation_letters (user_id, COALESCE(program_id, ''), content_hash)
    WHERE status = 'completed';
