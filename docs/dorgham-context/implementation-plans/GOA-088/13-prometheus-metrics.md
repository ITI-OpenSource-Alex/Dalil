# Task 13: `goa_ingestion_structured_rows_total` Prometheus Counter

## Objective
Add a new Prometheus counter, `goa_ingestion_structured_rows_total`, labeled `table`
(`program_requirements`|`scholarship_programs`), to the ingestion service's metrics module, and
increment it at each successful structured-row upsert in Task 12's wiring.

## Background
`services/ingestion/app/core/metrics.py` currently defines three metrics, all following the
`goa_ingestion_<noun>_total`/`_seconds` naming convention:

```
DOCS_PROCESSED_TOTAL = Counter("goa_ingestion_docs_processed_total", ..., ["source", "outcome"])
EMBEDDING_TOKENS_TOTAL = Counter("goa_ingestion_embedding_tokens_total", ..., ["source"])
RUN_DURATION_SECONDS = Gauge("goa_ingestion_run_duration_seconds", ...)
```

No counter exists today for structured-row upserts — GOA-086's visa upserts are only reflected in the
`visa_requirements_upserted`/`failed` counts inside the per-run report/log, not in Prometheus. GOA-088
explicitly asks for a dedicated Prometheus counter, which this task adds following the same naming and
labeling convention as the existing metrics.

## Scope
- `services/ingestion/app/core/metrics.py` (edited — one new `Counter` definition)
- `services/ingestion/app/services/run_orchestrator.py` (increment call sites — coordinated with
  Task 12, may be implemented as part of the same PR)

## Implementation Steps
- [ ] Add to `services/ingestion/app/core/metrics.py`:
      a `Counter` named `goa_ingestion_structured_rows_total`, description "Total number of structured
      rows upserted during ingestion", with a single label `table`, matching the existing file's
      `Counter(name, description, [labels])` construction style.
- [ ] In Task 12's orchestrator wiring, increment this counter once per successful
      `upsert_program_requirement` call with `table="program_requirements"`, and once per successful
      `upsert_scholarship_program` call with `table="scholarship_programs"` — placed at the same point
      in the loop as the existing `report["..._upserted"] += 1` increments, so a failed upsert does not
      also increment the metric (metric and report counter should stay in sync).
- [ ] Per the ticket's literal label enum (`program_requirements|scholarship_programs`), do **not**
      retroactively add a `table="visa_requirements"` increment to GOA-086's existing visa-upsert call
      site in this task — that is a separate, optional observability improvement (see master plan's
      Future Improvements), not part of this ticket's stated scope.

## Expected Files/Modules
- `services/ingestion/app/core/metrics.py` (edited)
- `services/ingestion/app/services/run_orchestrator.py` (edited — increment call sites; same lines
  touched by Task 12, coordinate to avoid duplicate/conflicting edits if done as separate PRs)

## Dependencies
- Task 12 (the call sites this counter is incremented from are the same pop-and-upsert blocks Task 12
  adds) — in practice, Tasks 12 and 13 are implemented together in one PR, with this task's counter
  definition landing first (or simultaneously) so Task 12's increment calls have something to call.

## Risks
- **Metric/report-counter drift.** If the Prometheus increment and the report-dict increment
  (`report["program_requirements_upserted"] += 1`) are placed at slightly different points in the
  try/except block, they can silently diverge (e.g. one increments on a partially-successful call the
  other doesn't count) — keep both increments in the exact same code path, ideally adjacent lines.
- **Label cardinality**: only two label values are expected (`program_requirements`,
  `scholarship_programs`) — do not parameterize `table` from adapter-provided free text, which would
  risk unbounded cardinality; the label value should be a hardcoded literal at each of the two call
  sites, not derived from the record's own data.

## Definition of Done
- `goa_ingestion_structured_rows_total{table="program_requirements"}` increments by 1 for each
  successful `program_requirements` upsert during a run.
- `goa_ingestion_structured_rows_total{table="scholarship_programs"}` increments by 1 for each
  successful `scholarship_programs` upsert during a run.
- The counter is visible at the ingestion service's existing metrics endpoint/exporter (matching
  however `DOCS_PROCESSED_TOTAL` etc. are already exposed — no new exporter wiring needed since
  `prometheus_client`'s default registry already picks up any new `Counter` instance automatically).
- A failed upsert does not increment the counter.

## Acceptance Criteria
- Ticket's explicit acceptance criterion is satisfied: "`goa_ingestion_structured_rows_total`
  Prometheus counter with label `table` (`program_requirements`|`scholarship_programs`)."
- A test asserting the counter's value increases by the expected amount after a mocked ingestion run
  with known record counts per table (following whatever pattern, if any, existing tests use to assert
  on `DOCS_PROCESSED_TOTAL` — if no such pattern exists yet, a direct read of the counter's `_value`
  via the `prometheus_client` test utilities is acceptable).

## Notes for Implementation
- This is a small, low-risk task best implemented alongside Task 12 in the same PR rather than as a
  fully separate change, since its only consumers are Task 12's increment call sites.
- Do not rename or restructure the existing `DOCS_PROCESSED_TOTAL`/`EMBEDDING_TOKENS_TOTAL`/
  `RUN_DURATION_SECONDS` metrics while adding this one — purely additive.
