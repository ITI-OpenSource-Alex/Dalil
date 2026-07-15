# Task 02: Migration — Extend `program_requirements` for Upsert/Idempotency Support

## Objective
Add the schema GOA-088's own acceptance criteria implicitly require but its DDL section never
mentions: a unique constraint on `(university, degree_level, country)` for `program_requirements`,
plus the columns needed to support a `content_hash`-based idempotent upsert
(`content_hash`, `source_url`, `last_scraped_at`, `updated_at`).

## Background
GOA-088 requires `POST /internal/program-requirements` to be an idempotent upsert "keyed by
university + degree_level + country," idempotent "via content_hash." Reading
`services/rag/app/migrations/003_create_program_requirements.sql` and
`008_update_program_requirements.sql` directly shows the current `program_requirements` schema is:

```
id UUID PRIMARY KEY DEFAULT gen_random_uuid()
university VARCHAR(255) NOT NULL
country VARCHAR(100) NOT NULL
degree_level VARCHAR(100) NOT NULL
min_ects INTEGER NULL
min_gpa DECIMAL(4,2) NULL
min_ielts DECIMAL(3,1) NULL
required_citizenship VARCHAR(100) NULL
min_work_experience INTEGER NULL
```

There is **no unique constraint** on any column combination, and **no `content_hash`, `source_url`,
`last_scraped_at`, or `updated_at` columns exist at all**. The `ON CONFLICT (...) DO UPDATE ... WHERE
content_hash IS DISTINCT FROM EXCLUDED.content_hash` pattern used for `visa_requirements`
(`app/services/visa_service.py`) is structurally impossible against the table as it exists today —
there is nothing to conflict on and nothing to compare hashes against. This is hidden schema work:
GOA-088's ticket text gives a full DDL block for the *new* `scholarship_programs` table but says
nothing about altering the *existing* `program_requirements` table, even though its own acceptance
criteria depend on this alteration having happened. This task makes that gap explicit and closes it,
without changing the ticket's stated upsert key or idempotency approach.

## Scope
Only a new migration file altering `program_requirements`. No application (Python) code changes in
this task (schema/service/endpoint work is Tasks 03/05).

## Implementation Steps
- [ ] Re-verify `services/rag/app/migrations/` still tops out at `011_add_scholarship_programs.sql`
      (i.e. confirm Task 01 has landed) before naming this file `012`.
- [ ] Before adding the unique constraint, confirm the 3 existing seed rows from
      `008_update_program_requirements.sql` (Technical University Munich/Germany/Master, ETH
      Zurich/Switzerland/Master, Erasmus Mundus/Europe/Master) are distinct on
      `(university, degree_level, country)` — they are, but re-verify against whatever data is
      actually present in the target environment (local dev DBs may have additional manually-inserted
      test rows that could collide).
- [ ] Create `services/rag/app/migrations/012_add_program_requirements_upsert_support.sql`:
      - `ALTER TABLE program_requirements ADD COLUMN content_hash VARCHAR(64) NULL;`
      - `ALTER TABLE program_requirements ADD COLUMN source_url VARCHAR(500) NULL;`
      - `ALTER TABLE program_requirements ADD COLUMN last_scraped_at TIMESTAMP DEFAULT NOW();`
      - `ALTER TABLE program_requirements ADD COLUMN updated_at TIMESTAMP DEFAULT NOW();`
      - `ALTER TABLE program_requirements ADD CONSTRAINT uq_program_requirements UNIQUE (university, degree_level, country);`
- [ ] New columns are nullable / defaulted so the migration cannot fail against the existing 3 seed
      rows (they will simply have `content_hash`/`source_url` as `NULL` and `last_scraped_at`/
      `updated_at` set to the migration's execution time until the next ingestion run overwrites them).
- [ ] Do **not** edit `003_create_program_requirements.sql` or `008_update_program_requirements.sql`
      — append-only, same convention as every other migration in this codebase.

## Expected Files/Modules
- `services/rag/app/migrations/012_add_program_requirements_upsert_support.sql` (new)

## Dependencies
- Task 01 (for migration numbering only — no functional dependency on `scholarship_programs`).

## Risks
- **Constraint failure on unexpected duplicate data.** If any environment has manually-inserted
  `program_requirements` rows that duplicate `(university, degree_level, country)`, the
  `ADD CONSTRAINT` step will fail outright. Must be checked per-environment before applying, not
  assumed safe purely because the 3 shipped seed rows are distinct.
- **Scope creep temptation.** This task should add exactly the columns needed for the upsert pattern
  and nothing else — do not use this migration to "clean up" unrelated `program_requirements` columns
  (e.g. renaming, tightening nullability on existing fields) since that is outside GOA-088's stated
  acceptance criteria and would widen this ticket's blast radius unnecessarily.
- **This is genuinely additional scope versus a literal reading of the ticket.** Confirm with the
  ticket owner (see master plan's Open Questions) that altering `program_requirements` is accepted as
  in-scope for GOA-088 before merging, since the ticket's DDL section never mentions it.

## Definition of Done
- The migration applies cleanly on top of `001`–`011` with no errors, including against a database
  containing the 3 existing seed rows.
- `\d program_requirements` shows the 4 new columns and the new unique constraint.
- Inserting two rows with the same `(university, degree_level, country)` triple fails with a unique
  violation.
- The 3 existing seed rows are untouched in every other column after the migration runs.

## Acceptance Criteria
- `program_requirements` supports the same `ON CONFLICT (...) DO UPDATE ... WHERE content_hash IS
  DISTINCT FROM EXCLUDED.content_hash` upsert shape already used by `visa_requirements`, without any
  further schema changes needed in Task 05.
- No data loss or corruption of the 3 pre-existing seed rows.

## Notes for Implementation
- Task 05 (`program_requirements` upsert service/endpoint) directly depends on this migration — do
  not start Task 05 until it is merged.
- This task does not change GOA-088's stated upsert key (`university + degree_level + country`) or
  its `content_hash`-based idempotency approach — it only adds the schema needed to actually implement
  what the ticket already specifies.
- If the `content_hash`/`last_scraped_at` semantics decision from Task 05/06 (always update
  `last_scraped_at`, even on an unchanged hash) changes how these columns are used, that does not
  require revisiting this migration — the columns as defined here support either semantic.
