# Task 01: Migration — Add `egyptian_specific` Column to `visa_requirements`

## Goal
Add the missing `egyptian_specific BOOLEAN` column to the existing `visa_requirements` table via a
new, additive SQL migration.

## Why this task exists
GOA-086's acceptance criteria list `egyptian_specific` as a required column on `visa_requirements`.
Investigation of the actual codebase found that migration `007_add_visa_requirements.sql` already
creates the table but omits this column. Every downstream write in this ticket (the service-layer
upsert in Task 03, and all 9 adapters in Tasks 07–15) needs this column to exist before it can
persist a value into it.

## Prerequisites
- None — this is the first task in the sequence.
- Read access to `services/rag/app/migrations/` to confirm the current migration head.

## Scope
Only a new migration file. No application code (Python) changes in this task.

## Implementation Steps
- [ ] Re-verify `services/rag/app/migrations/` still tops out at `008_update_program_requirements.sql`
      (re-check for drift since this plan was written — do not assume the plan's snapshot is current).
- [ ] Re-open `007_add_visa_requirements.sql` and confirm it still lacks an `egyptian_specific`
      column.
- [ ] Create `services/rag/app/migrations/009_add_egyptian_specific_to_visa_requirements.sql`
      containing:
      `ALTER TABLE visa_requirements ADD COLUMN egyptian_specific BOOLEAN NOT NULL DEFAULT FALSE;`
- [ ] Do **not** edit `007` or `008` — migrations in this codebase are append-only.
- [ ] Confirm no application code needs to change for the migration runner to pick this up (the
      runner executes files in numeric order at startup per GOA-006's design — no runner changes
      expected).

## Files Expected to Change
- `services/rag/app/migrations/009_add_egyptian_specific_to_visa_requirements.sql` (new)

## Acceptance Criteria
- The new migration applies cleanly on top of `001`–`008` with no errors.
- `visa_requirements.egyptian_specific` exists, is `BOOLEAN NOT NULL`, and defaults to `FALSE`.
- Any pre-existing rows in `visa_requirements` (e.g. from manual local testing) end up with
  `egyptian_specific = FALSE` after the migration runs, not `NULL`.
- `007_add_visa_requirements.sql` and `008_update_program_requirements.sql` are unmodified.

## Testing
- Start the local `rag_db` (docker-compose), let the migration runner execute all files, then run
  `\d visa_requirements` in `psql` and confirm the new column with its type/default/not-null.
- In a scratch/test database: insert a row via raw SQL before applying migration `009`, apply it,
  and confirm the pre-existing row now shows `egyptian_specific = FALSE` (not `NULL`, not an error).

## Notes
- Task 03 (visa_service upsert) directly depends on this column existing — do not start Task 03
  until this migration is merged.
- If a different default (e.g. nullable, or `TRUE`) is ultimately preferred, that's a deviation from
  this plan and should be confirmed with the ticket owner before changing it here, since it affects
  every other task that writes to this table.
