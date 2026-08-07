-- Seed the demo account's replicated profile row for opportunity matching.
--
-- Demo-readiness plan doc 03 (docs/dorgham-context/implementation-plan/
-- demo-readiness-plan/03-opportunity-matching-seed.md): match_programs()
-- (app/services/scoring.py) 425s with "Profile not yet replicated" for any
-- user_id with no row here, and local_user_profiles is populated
-- exclusively by an SQS consumer reacting to UserUpdated events -- the user
-- service has no profile-update endpoint at all, so there is currently no
-- in-product path that could ever create this row. Without this seed,
-- opportunity matching (the product's headline demo flow) always errors.
--
-- Placeholder UUID: the demo account does not exist (and therefore has no
-- UUID) until it is registered through the actual product, which happens
-- after this migration is authored. Ship with an all-zeros placeholder and
-- update it once per demo-account registration -- see
-- docs/dorgham-context/DEMO_RUNBOOK.md for the exact command. Re-run that
-- command any time the demo account is re-registered (e.g. a fresh account
-- per rehearsal run).
--
-- degree_level deviates from the implementation plan's literal 'Bachelor'
-- value -- see the DEMO_RUNBOOK.md "Opportunity Matching Seed Data" section
-- for the full, verified reasoning: check_hard_gates() (app/services/
-- gates.py) treats degree_level as an EXACT-EQUALITY gate against the
-- program's stated degree_level, not a "meets minimum" comparison. With
-- degree_level='Bachelor' here, every 'Master' program in the catalog --
-- including the three pre-existing seed programs this same profile is
-- meant to match against -- would hard-gate-block outright, leaving zero
-- non-blocked results and directly violating this document's own
-- acceptance criterion of returning programs across three distinct
-- confidence bands. 'Master' is used instead, verified against gates.py
-- and against 029_seed_demo_programs.sql's values before this file was
-- finalized.
INSERT INTO local_user_profiles (
    user_id,
    ects,
    gpa,
    gpa_scale,
    ielts_score,
    degree_level,
    work_exp,
    extracurriculars,
    target_countries,
    field_of_study
)
VALUES (
    '00000000-0000-0000-0000-000000000000', -- REPLACE via DEMO_RUNBOOK.md after registering the demo account
    180,
    3.45,
    '4.0',
    6.5,
    'Master',
    1,
    8,
    ARRAY['Germany', 'Switzerland', 'Netherlands'],
    'Computer Science'
)
ON CONFLICT (user_id) DO UPDATE SET
    ects = EXCLUDED.ects,
    gpa = EXCLUDED.gpa,
    gpa_scale = EXCLUDED.gpa_scale,
    ielts_score = EXCLUDED.ielts_score,
    degree_level = EXCLUDED.degree_level,
    work_exp = EXCLUDED.work_exp,
    extracurriculars = EXCLUDED.extracurriculars,
    target_countries = EXCLUDED.target_countries,
    field_of_study = EXCLUDED.field_of_study;
