# Task 01: Migration — Create `scholarship_programs` Table

## Objective
Add the new `scholarship_programs` table to `rag_db` via a new, additive SQL migration, exactly per
GOA-088's DDL, correctly numbered against the repository's actual current migration head.

## Background
GOA-088's acceptance criteria require a new `scholarship_programs` table, and its ticket text names
the migration file `008_add_scholarship_programs.sql`. Reading the repository directly
(`services/rag/app/migrations/`) shows migrations already run through
`010_seed_egypt_faq_entries.sql` — `008` is `008_update_program_requirements.sql`, already applied.
The ticket's filename is stale relative to repository state and must not be used literally. This
table does not exist anywhere yet — there is no prior migration, model, or code referencing
`scholarship_programs` in the codebase.

## Scope
Only a new migration file. No application (Python) code changes in this task. No changes to any
other migration file.

## Implementation Steps
- [ ] Re-verify `services/rag/app/migrations/` still tops out at `010_seed_egypt_faq_entries.sql`
      (re-check for drift since this plan was written — do not assume this plan's snapshot is
      current).
- [ ] Create `services/rag/app/migrations/011_add_scholarship_programs.sql` containing the ticket's
      DDL verbatim:
      - `id UUID PRIMARY KEY DEFAULT gen_random_uuid()`
      - `name VARCHAR(255) NOT NULL`
      - `provider VARCHAR(255) NOT NULL`
      - `country VARCHAR(100)`
      - `degree_level VARCHAR(100)`
      - `award_amount VARCHAR(255)` (free-text — award structures vary too much for a numeric column)
      - `deadline DATE`
      - `eligibility JSONB NOT NULL DEFAULT '{}'`
      - `citizenship_eligible BOOLEAN DEFAULT TRUE`
      - `min_gpa DECIMAL(4,2)`
      - `min_ielts DECIMAL(3,1)`
      - `source_url VARCHAR(500) NOT NULL`
      - `content_hash VARCHAR(64) NOT NULL`
      - `last_scraped_at TIMESTAMP DEFAULT NOW()`
      - `updated_at TIMESTAMP DEFAULT NOW()`
      - `UNIQUE (provider, name)`
- [ ] Do **not** edit any of `001`–`010` — migrations in this codebase are append-only, enforced in
      practice by `app/core/database.py::run_migrations`, which tracks executed filenames in a
      `migrations_log` table and only ever runs files not already recorded there.
- [ ] Confirm no application code needs to change for the migration runner to pick this up — it globs
      `app/migrations/*.sql`, sorts by filename, and runs anything not yet in `migrations_log` at
      service startup (`Database.connect()` → `run_migrations()`), same as every prior migration.

## Expected Files/Modules
- `services/rag/app/migrations/011_add_scholarship_programs.sql` (new)

## Dependencies
None — this is the first task in the GOA-088 sequence. It has no code dependency on Task 02, but
Task 02 should be numbered `012` to follow it sequentially.

## Risks
- **Filename collision if unverified.** Using the ticket's literal `008_...` name would either fail
  outright (file already exists) or, worse, be given a different name that collides with another
  in-flight branch's migration if `010` is no longer the actual head by the time this is implemented.
  Always re-check the migration directory immediately before naming the file.
- **DDL drift from the ticket.** This task should reproduce the ticket's DDL exactly — no schema
  redesign (e.g. do not add extra columns or constraints beyond what's specified here; any such
  changes belong in Task 02 for `program_requirements`, or should be raised as an open question rather
  than silently added here).

## Definition of Done
- The new migration applies cleanly on top of `001`–`010` with no errors.
- `\d scholarship_programs` shows every column from the ticket's DDL with matching types, defaults,
  and nullability, plus the `UNIQUE (provider, name)` constraint.
- `migrations_log` contains a row for `011_add_scholarship_programs.sql` after the service starts.
- No existing migration file is modified.

## Acceptance Criteria
- A fresh `rag_db` (migrations run from scratch) and an existing `rag_db` (migrations run
  incrementally from `010`) both end up with an identical `scholarship_programs` schema.
- Inserting a row with all `NOT NULL` fields populated succeeds; omitting `name`, `provider`,
  `source_url`, or `content_hash` fails with a constraint violation (proves `NOT NULL` is correctly
  applied).
- Inserting two rows with the same `(provider, name)` pair fails on the second insert with a unique
  violation (proves the constraint is live, ahead of Task 06's `ON CONFLICT` upsert relying on it).

## Notes for Implementation
- Task 06 (`scholarship_programs` upsert service) directly depends on this table and its unique
  constraint existing — do not start Task 06 until this migration is merged.
- This task intentionally does not touch `program_requirements` — that table's schema gap is handled
  separately in Task 02, kept as its own migration for clean, independently-revertable history.
- `notifications_sent` is not created, altered, or referenced by this migration — it does not exist in
  the repository and is out of scope for GOA-088 (see the master plan's Context section).
