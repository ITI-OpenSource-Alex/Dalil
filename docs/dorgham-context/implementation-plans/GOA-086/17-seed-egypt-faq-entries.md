# Task 17: Seed 6 Egypt-Specific FAQ Entries

## Goal
Seed the existing `faq_entries` table with 6 hand-curated Egypt-specific question/answer pairs via a
new migration.

## Why this task exists
GOA-086 requires 6 FAQ seed entries covering common Egypt-specific visa questions. The
`faq_entries` table already exists (migration `005_create_faq_entries.sql`) but is currently empty
and — per the main plan's investigation — entirely unused by application code.

## Prerequisites
- None technical — the `faq_entries` table already exists and this task only inserts rows.
- Independent of all other tasks in this breakdown; can be done at any point, in parallel with
  anything else.

## Scope
One new migration file containing `INSERT` statements only. No application code changes.

## Implementation Steps
- [ ] Draft 6 question/answer pairs covering: APS certificate necessity, Sperrkonto minimum balance,
      Thanaweya Amma recognition, Egyptian Police Criminal Record Certificate, VFS Global Egypt
      appointment process, and military status certificate — matching the Egypt-specific context
      items named in the ticket.
- [ ] Create `services/rag/app/migrations/010_seed_egypt_faq_entries.sql` with
      `INSERT INTO faq_entries (question_pattern, answer_markdown, sources, category) VALUES (...)`
      for all 6 rows, matching the schema from migration `005`
      (`question_pattern TEXT`, `answer_markdown TEXT`, `sources JSONB DEFAULT '[]'`,
      `category VARCHAR(100)`).
- [ ] Set `category` consistently across all 6 rows (e.g. `'visa_egypt'`) so they're identifiable as
      a set for future maintenance/audit.
- [ ] Populate `sources` JSONB with real reference URLs where confirmed (see main plan Question #2
      on source URLs); leave `[]` if none are confirmed yet rather than fabricating links.
- [ ] Write real, substantive `answer_markdown` content — not placeholder text — since this is
      user-facing content if/when it becomes reachable.

## Files Expected to Change
- `services/rag/app/migrations/010_seed_egypt_faq_entries.sql` (new)

## Acceptance Criteria
- Migration runs cleanly after `009` (Task 01).
- `SELECT COUNT(*) FROM faq_entries WHERE category = 'visa_egypt'` returns exactly 6.
- Each row's `question_pattern` is phrased the way a real user might ask (relevant for future
  `pg_trgm` fuzzy matching, threshold 0.85, once that logic exists).
- `answer_markdown` content is accurate and complete for each of the 6 topics.

## Testing
- Run the migration locally against `rag_db`, query the 6 rows, and manually verify content
  accuracy and that `question_pattern` phrasing is realistic.
- No automated test is required for the seed data itself beyond confirming the migration applies
  without error and inserts exactly 6 rows — functional testing of *matching* these entries is out
  of scope here (see Notes).

## Notes
- **Important caveat carried over from the main plan**: seeding these rows does **not** make them
  reachable at query time. No code anywhere (`app/services/rag_service.py::query_rag()`) currently
  checks `faq_entries` before answering a query — that fuzzy-match-then-skip-LLM logic is GOA-045's
  scope, which is unimplemented. This task only satisfies the ticket's "6 FAQ entries seeded"
  acceptance criterion. The ticket's separate "verify FAQ cache hit" integration-test criterion is
  explicitly descoped to Task 18 pending GOA-045 (see main plan, Dependencies section and Question
  #1).
