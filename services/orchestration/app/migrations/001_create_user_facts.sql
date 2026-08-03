-- GOA-038 -- long-term conversation memory.
--
-- First table in orchestration_db. Short-term conversation state stays in Redis
-- with a 24-hour TTL (app/services/memory.py); this table is only for facts that
-- must survive a session ending.

CREATE TABLE IF NOT EXISTS user_facts (
    id              BIGSERIAL PRIMARY KEY,
    user_id         VARCHAR(255) NOT NULL,
    fact_type       VARCHAR(64)  NOT NULL,
    -- Discriminator within a fact_type, and the whole reason one unique index
    -- can express two different cardinality rules:
    --   single-valued types (degree, gpa, target_country) store ''
    --       -> one row per (user, type), so a new GPA replaces the old one
    --   multi-valued types (mentioned_program, concern) store the normalised value
    --       -> one row per distinct value, so two programs are two rows
    -- Getting this wrong in either direction breaks an acceptance criterion:
    -- collapse the multi-valued types and the user has exactly one "mentioned
    -- program"; split the single-valued ones and a corrected GPA becomes a
    -- duplicate rather than an update.
    fact_key        VARCHAR(255) NOT NULL DEFAULT '',
    fact_value      TEXT         NOT NULL,
    confidence      REAL         NOT NULL,
    source_session  VARCHAR(255),
    revision        INTEGER      NOT NULL DEFAULT 1,
    extracted_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    -- Bumped whenever an extraction re-confirms this value. Expiry is measured
    -- from here and not from extracted_at, because the AC says facts expire
    -- after 30 days "without reinforcement" -- a fact the user keeps repeating
    -- is not stale just because they first said it two months ago.
    reinforced_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),

    CONSTRAINT user_facts_confidence_range CHECK (confidence >= 0.0 AND confidence <= 1.0),
    CONSTRAINT user_facts_value_length     CHECK (char_length(fact_value) <= 512),
    -- The allow-list is in the database on purpose. Exam band scores are
    -- authoritative from the Exam service (app/services/exam_context.py); a
    -- self-reported band extracted from chat must never be able to land here and
    -- compete with a graded one. A prompt instruction alone is a request; this
    -- is a guarantee.
    CONSTRAINT user_facts_type_allowed     CHECK (fact_type IN (
        'degree', 'gpa', 'target_country', 'mentioned_program', 'concern'
    ))
);

CREATE UNIQUE INDEX IF NOT EXISTS user_facts_identity_uniq
    ON user_facts (user_id, fact_type, fact_key);

-- The read path: every live fact for one user, expiry filtered in SQL.
CREATE INDEX IF NOT EXISTS user_facts_user_reinforced_idx
    ON user_facts (user_id, reinforced_at DESC);
