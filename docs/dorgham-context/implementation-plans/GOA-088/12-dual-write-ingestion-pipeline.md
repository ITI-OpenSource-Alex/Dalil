# Task 12: Wire the 3 Adapters into `run_orchestrator.py`'s Dual-Write Pipeline

## Objective
Extend `run_orchestrator.py`'s per-document processing loop to pop `"program_requirements"` and
`"scholarship_programs"` keys off each doc dict (alongside the existing `"visa_requirements"` pop),
upsert each record independently via the Task 08 client functions, and isolate failures on each path
exactly as GOA-086's visa wiring already does.

## Background
`services/ingestion/app/services/run_orchestrator.py:86-108` already implements this exact mechanism
for visa records:

```python
for doc_dict in result:
    visa_records = doc_dict.pop("visa_requirements", [])
    for visa_record in visa_records:
        try:
            upsert_visa_requirement(visa_record)
            report["visa_requirements_upserted"] += 1
        except Exception as e:
            logger.error("visa_requirement_upsert_failed", ...)
            report["visa_requirements_failed"] += 1
    documents.append(Document(page_content=doc_dict.pop("content"), metadata=doc_dict))
```

This task adds two more pop-and-upsert blocks following the identical shape, for the two new keys
Tasks 09–11 attach. `MastersPortalAdapter` is already instantiated in `run_orchestrator.py`'s
`adapters = [...]` list (line 42); `DAADAdapter` and `CheveningAdapter` are too (lines 38-39) — no new
adapter registration is needed, only the new pop/upsert logic inside the existing loop.

## Scope
- `services/ingestion/app/services/run_orchestrator.py`

No changes to adapter files (Tasks 09–11, already complete by this point) or RAG-service code
(Tasks 01–06, already complete).

## Implementation Steps
- [ ] Import `upsert_program_requirement`, `upsert_scholarship_program` from `client.py` (Task 08),
      alongside the existing `from client import upsert_visa_requirement`.
- [ ] In the per-document loop (`run_orchestrator.py:86-108`), immediately after the existing
      `visa_records = doc_dict.pop("visa_requirements", [])` block and before the
      `Document(...)` construction, add two more pop-and-upsert blocks following the exact same shape:
      one popping `"program_requirements"` off `doc_dict` (default `[]`) and calling
      `upsert_program_requirement` per record inside a per-record `try/except`, and one popping
      `"scholarship_programs"` off `doc_dict` (default `[]`) and calling `upsert_scholarship_program`
      per record inside its own per-record `try/except` — mirroring the existing
      `visa_records`/`upsert_visa_requirement` block line-for-line, with `program_requirements_upserted`/
      `program_requirements_failed` and `scholarship_programs_upserted`/`scholarship_programs_failed`
      counters incremented in place of the existing `visa_requirements_upserted`/`visa_requirements_failed`
      ones.
- [ ] Initialize the 4 new report counters (`program_requirements_upserted/failed`,
      `scholarship_programs_upserted/failed`) in the `report = {...}` dict at the top of
      `run_ingestion()`, alongside the existing `visa_requirements_upserted/failed` keys.
- [ ] Increment the new Task 13 Prometheus counter (`STRUCTURED_ROWS_TOTAL.labels(table=...)`)
      alongside each successful upsert, one label per table.
- [ ] Extend the final `logger.info("ingestion_run_completed", ...)` call (`run_orchestrator.py:136-144`)
      to include the 4 new counts, matching how `visa_requirements_upserted/failed` are already logged.
- [ ] Confirm the existing per-adapter isolation
      (`asyncio.gather(*[adapter.scrape() for adapter in adapters], return_exceptions=True)`,
      `run_orchestrator.py:55`) already wraps `MastersPortalAdapter`/`DAADAdapter`/`CheveningAdapter`
      identically to every other adapter — no special-casing needed, this task only adds logic inside
      the existing per-document loop, not a new concurrency primitive.

## Expected Files/Modules
- `services/ingestion/app/services/run_orchestrator.py` (edited)

## Dependencies
- Task 08 (`client.py`'s `upsert_program_requirement`/`upsert_scholarship_program` functions must
  exist to import).
- Tasks 09, 10, 11 (all 3 adapters must attach their respective structured-record keys for this
  wiring to have anything to pop).
- Task 13 (metrics counter — can be stubbed/deferred slightly, but should land before or alongside
  this task since the increment call sites are added here).

## Risks
- **Breaking the existing visa dual-write pipeline while editing the same function.** This task edits
  the same loop GOA-086's visa wiring lives in — the visa pop/upsert block, its report counters, and
  its log fields must remain completely untouched (regression risk is proportional to how surgically
  the new blocks are inserted next to, not interleaved with, the existing one).
- **Failure isolation must hold across three structured-record types simultaneously.** A single
  `doc_dict` from `MastersPortalAdapter` will only ever have a `"program_requirements"` key (never
  `"scholarship_programs"` or `"visa_requirements"`), and vice versa for DAAD/Chevening — but the loop
  processes all adapters' results through the same code path, so all three `.pop(..., [])` calls must
  be safe no-ops for adapters that never set that key (guaranteed by Python's `dict.pop` default-value
  behavior, but must be verified in the actual diff, not assumed).
- **`handler.py`**: GOA-086's plan noted a second, separate hardcoded adapter list in
  `services/ingestion/handler.py::fetch_all_adapters`, duplicating `run_orchestrator.py`'s adapter
  list and dual-write logic. Confirm whether `handler.py` still exists and still duplicates this logic
  at implementation time — if so, this task's wiring needs to be applied there too for consistency,
  matching how GOA-086 duplicated its own wiring in both places rather than leaving one path stale.

## Definition of Done
- Running the full pipeline (fixture-mode) processes `MastersPortalAdapter`, `DAADAdapter`, and
  `CheveningAdapter` alongside all existing adapters.
- Each adapter's structured records are POSTed individually to the correct RAG endpoint via the Task
  08 client functions.
- A simulated failure in one structured-upsert call does not prevent other records, other adapters, or
  the document-chunk pipeline from completing — matching the existing visa-record isolation guarantee.
- The completion report/log includes accurate `program_requirements_upserted/failed` and
  `scholarship_programs_upserted/failed` counts.
- The existing `visa_requirements_upserted/failed` behavior and counts are completely unaffected
  (regression check).

## Acceptance Criteria
- Ticket's explicit integration-test wording is satisfied: "an ingestion run populates both
  `program_requirements` and `scholarship_programs` and writes chunked documents from the same
  sources."
- Integration tests extending `tests/test_orchestrator.py`'s existing patterns: mock all 3 adapters'
  `scrape()` to return fixture output including populated structured keys; assert the correct client
  function is called once per accumulated record; force an exception from one upsert call and assert
  the run still completes with the failure reflected in the report; confirm the existing 12 adapters'
  (6 GOA-015 + visa/Egypt adapters from GOA-086) behavior is unaffected.

## Notes for Implementation
- This task is the concrete implementation of GOA-088's dual-write requirement — recovery from a
  partial failure is simply re-running the pipeline on the next scheduled/manual ingestion pass,
  relying on both sides' idempotency (unique keys on `program_requirements`/`scholarship_programs`,
  existing chunk-document idempotency), exactly matching GOA-086's "no 2PC/saga" resolution.
- This task is a hard prerequisite for Task 17 (integration and regression testing).
