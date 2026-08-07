-- Expand program_requirements for the opportunity-matching demo.
--
-- Demo-readiness plan doc 03: only 3 programs existed before this migration
-- (008_update_program_requirements.sql: TU Munich, ETH Zurich, Erasmus
-- Mundus) -- thin for a feature described as scoring the European
-- catalogue, and none of them alone demonstrate a *range* of match
-- confidence. This adds 9 rows tuned deliberately (not arbitrarily)
-- against the exact demo profile seeded in
-- 028_seed_demo_user_profile.sql, verified with a standalone calculator
-- script that replicates app/services/soft_score.py's exact formula before
-- these values were finalized (see DEMO_RUNBOOK.md for the full numbers).
--
-- degree_level is 'Master' on every row, matching the profile seed's
-- degree_level (see 028's header comment for why) -- check_hard_gates()
-- treats degree_level as an exact-equality gate, so any mismatch here
-- would silently block that row for the demo account regardless of every
-- other value.
--
-- discipline is 'computer_science' on every row, matching exactly what
-- discipline_for_field_of_study('Computer Science') returns (app/services/
-- scoring.py) -- match_programs()'s candidate query excludes any row whose
-- discipline is set to something else, so a mismatch here would silently
-- drop the row from every /match response for this profile.
--
-- Country spread follows the implementation plan's literal instruction
-- ("across Germany, Netherlands, Sweden, Italy, and Canada"), but note:
-- the demo profile's target_countries is {Germany, Switzerland,
-- Netherlands} (028), and match_programs()'s candidate query filters
-- candidates by exact country membership in that list before scoring ever
-- runs. The Sweden/Italy/Canada rows below (KTH, Politecnico di Milano,
-- University of Toronto) will therefore NEVER appear in a /match response
-- for the demo account -- they exist in the catalog (supporting the wider
-- "we score the European catalogue" narrative and remaining available if
-- the demo profile's target countries are ever changed) but are inert for
-- the actual demo run. This is a verified consequence of following both of
-- the implementation plan's instructions literally, not an oversight --
-- see DEMO_RUNBOOK.md for the full explanation.
--
-- Score tiers actually achieved for the demo profile (verified against a
-- standalone calculator replicating compute_soft_score exactly -- see
-- DEMO_RUNBOOK.md): the highest realistically achievable score for this
-- profile is ~70, not the platform's literal "green >= 80" card-color
-- threshold -- see DEMO_RUNBOOK.md for why that ceiling exists and cannot
-- be closed by seed-value tuning alone without either changing the
-- profile's stated GPA/IELTS (fixed by the implementation plan) or
-- modifying the scoring formula's weights (explicitly out of scope for
-- this task). The tiers below are relatively, not absolutely, high/mid/low.
--
-- source_url: the implementation plan (and 014_add_program_requirements_
-- upsert_support.sql, written before this table's unique identity moved)
-- assumed idempotency was keyed on (university, degree_level, country).
-- 020_program_source_url_identity.sql re-keyed it to source_url instead
-- (dropping uq_program_requirements and adding
-- uq_program_requirements_source_url) -- verified directly against the
-- live schema (`\d program_requirements`) after `ON CONFLICT (university,
-- degree_level, country)` failed at startup with "no unique or exclusion
-- constraint matching the ON CONFLICT specification". Each row below gets
-- a distinct internal-namespace source_url, following the same
-- 'https://goa.internal/seed/...' convention 020's own backfill used for
-- the original three seed programs, and the ON CONFLICT clause matches
-- the constraint that actually exists today.
INSERT INTO program_requirements (
    university,
    country,
    degree_level,
    program_name,
    deadline,
    discipline,
    min_ects,
    min_gpa,
    min_ielts,
    min_work_experience,
    source_url
)
VALUES
    -- Highest-scoring tier for the demo profile (~68-70): generous,
    -- fully- or mostly-stated requirements the profile clears with margin
    -- on every judgeable dimension.
    ('Technical University of Berlin', 'Germany', 'Master',
     'MSc Computer Science', '2026-10-15', 'computer_science',
     90, 2.3, 5.5, 0,
     'https://goa.internal/seed/demo-program/tu-berlin-msc-cs'),
    ('Vrije Universiteit Amsterdam', 'Netherlands', 'Master',
     'MSc Artificial Intelligence', '2026-09-01', 'computer_science',
     100, 2.5, 5.5, 0,
     'https://goa.internal/seed/demo-program/vu-amsterdam-msc-ai'),
    ('RWTH Aachen University', 'Germany', 'Master',
     'MSc Data Science', '2026-11-30', 'computer_science',
     100, 2.7, 6.0, NULL,
     'https://goa.internal/seed/demo-program/rwth-aachen-msc-ds'),
    ('University of Twente', 'Netherlands', 'Master',
     'MSc Computer Science', '2026-12-15', 'computer_science',
     90, NULL, 5.5, NULL,
     'https://goa.internal/seed/demo-program/twente-msc-cs'),

    -- Mid tier for the demo profile (~63-65): tighter margins against the
    -- profile's stated GPA/ECTS/IELTS.
    ('Delft University of Technology', 'Netherlands', 'Master',
     'MSc Computer Science', '2027-01-15', 'computer_science',
     178, 3.4, 6.5, 3,
     'https://goa.internal/seed/demo-program/delft-msc-cs'),

    -- Seeded for catalog breadth per the implementation plan's literal
    -- country list; inert for the demo account -- see header comment.
    ('KTH Royal Institute of Technology', 'Sweden', 'Master',
     'MSc Computer Science', '2026-10-01', 'computer_science',
     175, 3.3, 6.5, NULL,
     'https://goa.internal/seed/demo-program/kth-msc-cs'),
    ('Politecnico di Milano', 'Italy', 'Master',
     'MSc Computer Engineering', '2026-11-01', 'computer_science',
     150, 3.3, 6.5, 2,
     'https://goa.internal/seed/demo-program/polimi-msc-ce'),
    ('University of Toronto', 'Canada', 'Master',
     'MSc Computer Science', '2026-12-01', 'computer_science',
     160, 3.4, 6.5, 2,
     'https://goa.internal/seed/demo-program/toronto-msc-cs'),

    -- Deliberately fails the demo profile's ECTS hard gate (profile has
    -- 180; this requires 210) so the demo can show a genuinely blocked
    -- card with a real, computed reason -- not three uniformly "passing"
    -- cards. Matches this implementation plan document's own illustrative
    -- example almost verbatim ("your ECTS credits (180) are below the
    -- minimum required (210)").
    ('University of Stuttgart', 'Germany', 'Master',
     'MSc Computer Science', '2026-10-20', 'computer_science',
     210, 3.0, 6.0, 0,
     'https://goa.internal/seed/demo-program/stuttgart-msc-cs')
ON CONFLICT (source_url) DO NOTHING;
