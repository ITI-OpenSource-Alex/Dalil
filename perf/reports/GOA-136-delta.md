# GOA-136 — pre/post delta

**Ticket:** GOA-136 — Evals: independent judge, self-consistency, and label provenance

**Branch:** `feat/GOA-133-137-architecture-remediation`

**Harness:** `perf/eval_integrity_bench.py`, SHA-256 `C2FE174836729FDDC106B7D1EBEFA6438959541052FFFAF4D7AD4836CBE8F95C` (one exact file, run twice)

**Artefacts:** `GOA-136-pre-20260807T224643Z.json` · `GOA-136-post-20260807T235359Z.json`

Both benchmark runs are valid: 15/15 real Writing grader calls, zero grader
cache hits, zero grader errors, and `real: true` for the graders, same-family
judge, and independent judge.

## Acceptance delta

| ID | Metric | PRE | POST | Target | Verdict |
|---|---|---|---|---|---|
| E1 | Writing accuracy / MAE | 66.67% / 0.500, n=3 | 33.33% / 0.667, n=3 plus adjacent caveat | Preserve measured value; publish n/provenance | ✅ structure · ❌ 80% floor |
| E2 | Speaking accuracy | `null`, no reason in schema | `null`, explicit PCM/audio reason, pipeline not exercised | Null with reason or real measured value | ✅ |
| E3 | Model identity in report schema | absent | independent `gpt-5.6-sol`; graders `claude-opus-4-8` | Present and different families | ✅ |
| E4 | Label provenance in report schema | absent | writing, synthetic writing, and speaking each carry total/validated/synthetic/source | All four provenance fields | ✅ |
| E5 | Consistency in report schema | absent | present per domain, item, and criterion | Present | ✅ |
| E6 | Mean per-item band stddev | 0.2299 | 0.1483 | Publish; no pass threshold | ✅ published |
| E6 | Max spread / unanimous rate | 0.5 / 0% | 0.5 / 33.33% | Publish; do not tune | ✅ published |
| E8 | Judge-family verdict delta | 0 changed | 0 changed | Publish both arms and delta | ✅ |
| E9 | Incremental judge cost in harness | $0 same-family cache; $0.031146 independent | $0 both arms (all cached) | Record, do not infer zero total cost | ✅ with cache caveat |
| — | WebSocket failure semantics | fabricated band `0.0` | `null` plus error | Never collapse unknown into zero | ✅ |

The accuracy change is **not attributed to GOA-136**. The grader is stochastic,
the validated set is only three rows, and a single verdict moves the percentage
by 33 points. That is exactly why the mandatory report caveat reads
`n=3 — not a validation; see band_source`. The fixed 80% floor was not relaxed:
the actual runner exits 1 with `FLOOR: writing accuracy 66.7% is below the 80%
target (2/3)`.

## Self-consistency detail

All figures below are from the same frozen 15-call harness.

| Criterion | PRE stddev | POST stddev | PRE max spread | POST max spread |
|---|---:|---:|---:|---:|
| Coherence | 0.1333 | 0.0667 | 1.0 | 0.5 |
| Grammar | 0.2545 | 0.1333 | 1.0 | 1.0 |
| Lexical | 0.2064 | 0.1870 | 1.0 | 1.0 |
| Task response | 0.3397 | 0.2730 | 1.0 | 1.0 |

The separately executed production report flow also completed 15/15 repeats
with no errors: mean per-item stddev **0.215**, max spread **0.5**, and unanimous
rate **0%**. Its corrected GOA-135 Redis telemetry recorded **64,347 input** and
**240,444 output tokens**, priced by the shared table at **$7.599402**. Missing
telemetry is represented as null plus a reason; this run had real counters and a
real priced value.

The 5× consistency setting is therefore materially expensive. It remains opt-in
behind `--consistency --repeats 5`; the default CI path does not incur it.

## Judge-family interpretation

Both PRE and POST changed **zero verdicts** between `claude-opus-4-8` and
`gpt-5.6-sol`, so the headline verdict is not merely same-family agreement in
this tiny set. The judged bands were not identical: PRE differed by 0.5 on two
rows; POST differed by 0.5 and 1.0 on two rows. The report publishes those
per-item differences rather than treating the zero verdict delta as proof that
judge choice never matters.

## Speaking honesty

The original transcript replay client does not match production. The Gateway
route expects `session_init` followed by binary PCM audio; the dataset contains
synthetic transcripts and no audio. GOA-136 therefore does not fabricate a
speaking score. It reports `speaking_accuracy: null`,
`speaking_pipeline_exercised: false`, and the reason adjacent to **NOT MEASURED**.
Connection and timeout paths in `ws_client.py` also return null, never `0.0`.

## Verification

| Check | Result |
|---|---|
| Eval suite in disposable container | **66 passed, 1 expected xfail** |
| Writing prerequisite suite in service container | **84 passed, 3 skipped** |
| Actual eval report flow | JSON + HTML generated; 15/15 consistency; expected floor exit 1 |
| Rendered HTML visual QA | Caveat is high-contrast and immediately below 66.7%; model, provenance, consistency cost, speaking reason, and item rows are readable |
| Harness parity | PRE and POST executable SHA-256 identical |

GOA-028's tracked plan now records what was actually measured. GOA-138 is filed
to expand the examiner-validated writing set from 3 to 20 and carries GOA-028
Task 1's copyright guidance verbatim.
