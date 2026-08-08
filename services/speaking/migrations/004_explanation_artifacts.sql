-- SPEAK-EVAL-008: immutable explanation artifacts.
--
-- The acceptance criterion is "history does not regenerate explanations". That
-- is a storage decision before it is a rendering one.
--
-- Regenerating an explanation at read time would produce different text for the
-- same band on every visit: the model is not deterministic, the prompts change
-- as we tune them, and the frozen rubric is versioned. A student who is told
-- "band 6 because you paused five times" and returns next week to "band 6
-- because your vocabulary was limited" has been given two different reasons for
-- one score, and has no way to know which one was real.
--
-- So the explanation shown at scoring time is written once and read forever.
-- The table has no UPDATE path by design.

CREATE TABLE IF NOT EXISTS speaking_explanations (
    session_id      TEXT PRIMARY KEY
                    REFERENCES speaking_sessions(id) ON DELETE CASCADE,

    -- The renderable projection exactly as it was shown, including the claims
    -- that were withheld. Storing only what was displayed would lose the record
    -- that something was suppressed, and "why did this session show less?" is a
    -- question worth being able to answer.
    renderable      JSONB NOT NULL,

    -- Provenance of the explanation itself, not of the score. Which rubric
    -- version was cited, which scorer build produced it, which model. Two
    -- explanations for the same band are only comparable if these match.
    rubric_id       TEXT NOT NULL,
    rubric_version  TEXT NOT NULL,
    rubric_sha256   TEXT,
    scorer_version  TEXT NOT NULL,
    llm_model       TEXT,

    -- Counts, denormalised so history listings can show "2 unverified" without
    -- parsing the JSONB of every row.
    claim_count     INTEGER NOT NULL DEFAULT 0,
    withheld_count  INTEGER NOT NULL DEFAULT 0,

    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ON DELETE CASCADE above, deliberately: an explanation for a deleted session is
-- orphaned personal data. GOA-046's account deletion removes the session, and
-- this must go with it rather than survive as a transcript quote with no owner.

CREATE INDEX IF NOT EXISTS idx_speaking_explanations_created_at
    ON speaking_explanations (created_at DESC);
