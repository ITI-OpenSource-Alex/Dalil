# GOA-134 — pre/post delta

**Ticket:** GOA-134 — Speaking + Exam: holistic aggregate-band contract, timeout chain, result persistence
**Branch:** `feat/GOA-133-137-architecture-remediation`
**Harness:** `services/speaking/agents/holistic_contract_test.go` (one file, run twice)
**Artefacts:** `GOA-134-pre-matrix.md` · `GOA-134-post-matrix.md`

---

## The band contract

Fault-injection matrix, asserted on the **serialised JSON** rather than the Go
struct — `omitempty` behaviour is what a client sees, and a struct-level
assertion would pass while the wire format was wrong.

| Completed criteria | PRE `overall_band` | PRE `completed_count` | POST `overall_band` | POST `completed_count` | ✅ |
|---|---|---|---|---|---|
| 4 of 4 | present, 7 | **absent** | present, 7 | 4 | ✅ |
| 3 of 4 | present, 7 | **absent** | present, 7 | 3 | ✅ |
| 2 of 4 | **present, 7** ❌ | absent | **absent** | 2 | ✅ |
| 1 of 4 | **present, 7** ❌ | absent | **absent** | 1 | ✅ |
| 0 of 4 | **present, 0** ❌ | absent | **absent** | 0 | ✅ |

Identical across all three failure modes — provider error, malformed JSON
(BUG-057's shape), and deadline exceeded.

The `0 of 4 → overall_band: 0` row is BUG-055 verbatim: a score the model never
produced, reported as a real one. `services/exam` then persisted it to
`exam_results.band_score` as the candidate's official IELTS speaking band.

## Cross-path divergence — closed

`TestSwarmAndHolisticAgreeOnBandContract` drives the identical fault matrix
through both `EvaluateSwarm` (streaming) and `EvaluateHolisticSwarm` (full exam).

**PRE:**
```
0 of 4 completed: holistic overall_band present=true but streaming present=false
1 of 4 completed: holistic overall_band present=true but streaming present=false
2 of 4 completed: holistic overall_band present=true but streaming present=false
```

**POST:** passes at every k. `MinCriteriaForOverallBand` is now *imported* by
`holistic.go` rather than absent from it — the constant was declared three files
away in the same package and never referenced.

This is the test that would have caught the original divergence, and it is the
most valuable artefact in the ticket.

## Error vs deadline classification

| | PRE | POST |
|---|---|---|
| Provider error | `TimedOut: true`, error **discarded**, nothing logged | `Error: <breadcrumb>`, logged at **ERROR** with `failed_after` |
| Malformed JSON | identical to a timeout | `Error: <breadcrumb>`, ERROR — raising the deadline can never fix it |
| Deadline | `TimedOut: true` | `Error: "deadline exceeded"`, logged at **WARN** |

`TimedOut` keeps its meaning of "produced no score" to match `swarm.go` and the
exam service's `CriterionDetail.timed_out` wire field; `Error` is the
discriminator. Renaming the field would be clearer and would break the contract
with services/exam — it belongs in the follow-up that merges the two paths.

## The timeout chain

| Link | PRE | POST |
|---|---|---|
| Exam → Speaking HTTP (`speaking_client.py`) | hardcoded `30.0` | `settings.speaking_evaluation_timeout_s` = **75s** |
| Speaking handler ctx (`holistic_handler.go`) | hardcoded `15*time.Second` | `swarmEvaluationTimeout` = **60s** |
| Measured p95 time-to-first-criterion (GOA-032) | 28,728 ms | — |

The inner deadline was roughly **half** what a *single* agent needs at p95, on a
path that grades the concatenated three-part transcript — larger prompts and
slower completions than the streaming path, not faster.

Raising the handler alone would not have worked: the exam client aborted at 30s.
`test_speaking_client_timeout_exceeds_speaking_swarm_budget` pins the invariant by
parsing `swarmEvaluationTimeout` out of `client.go` rather than duplicating it as
a literal — a duplicated constant is how these two drifted in the first place.

## The orphaned-session bug

`try_submit` flips the session to `submitted` **before** the speaking call. On
failure no result row was written, and the guard at the top of the endpoint
(`status in ("submitted", "scored") → return {}`) refused every retry. The
candidate's exam was unrecoverable and the endpoint returned **200**.

Fixed with `SessionRepository.revert_submission`, applied on any failure in the
critical section — the HTTP call *and* the persist. Deliberately narrow
(`WHERE status='submitted'`), so a session that reached `scored` concurrently is
never dragged backwards. The idempotency guard is **kept**: deleting it would
trade a lost exam for a double-graded one, and
`test_resubmit_guard_still_idempotent` guards against that "fix".

## Nullability through the chain

| Layer | PRE | POST |
|---|---|---|
| `EvaluationResponse.overall_band` | `float` (**required**) | `float \| None = None` |
| `exam_results.band_score` | `DECIMAL(3,1) NOT NULL` | nullable (migration `009`) |
| `ResultRepository.create` | `band_score: float` | `float \| None` |
| `models/exam_result`, `schemas/exam_result`, `schemas/history` | `float` | `float \| None` |
| `ExamResultResponse.band_score` (TS) | `number` | `number \| null` |
| Results page | `{result.band_score}` | `?? "—"` + "Not enough criteria completed to score" |
| Profile score post | posted unconditionally | **skipped when null** — would have overwritten a real band with nothing |

Migration verified against the populated dev database:

```
null_band_persisted
 t
ERROR:  column "band_score" of relation "exam_results" contains null values
```

The NULL inserts, and the rollback **fails loudly** while an unresolved NULL
exists — exactly as its comment says it should, rather than silently coercing to
0.0 and reintroducing the defect.

## Already-broken rows in the dev database

| Query | Result |
|---|---|
| Orphaned `submitted` sessions with no result (H6) | **0** |
| Speaking results with `band_score = 0.0` | **0** |
| Speaking results, total | **0** |

Nothing to repair — and the last row is itself corroboration: **the holistic path
has never once produced a result in this environment**, which is what a 15-second
budget against a 28.7-second p95 predicts.

## Tests

| Suite | Result |
|---|---|
| `services/speaking/...` (all packages) | **all ok** |
| `services/speaking/{agents,internal/speaking}` under `-race` | **ok** |
| `services/exam/tests/` (container) | **248 passed, 1 skipped, 0 failed** |
| `services/exam/tests/test_speaking_evaluation_contract.py` (new, 9 tests) | **all pass** |
| `services/frontend` `tsc --noEmit` | **clean** |

### A pre-existing test that demanded the defect

`TestHolisticSwarm_AllFailed` asserted `res.OverallBand == 0.0` — it pinned the
bug in place, the same pattern as the exam-stats test that "demanded the lie" in
this project's own warning list. Rewritten to assert the band is absent.

### Pre-existing failures, not caused by this change

- `services/exam/tests/test_grading_accuracy.py` fails at **collection**
  in-container: `Path(__file__).parents[3]` assumes the repo layout and the tests
  live at `/app/tests` inside the image. Same class as the issue fixed in
  `packages/pricing/py/tests` under GOA-135. Not in this ticket's scope; worth a
  follow-up since it means grading-accuracy is only ever run on a host.
- The exam suite requires `INTERNAL_API_KEY=test-internal-key`; `conftest.py` uses
  `setdefault`, so compose's `supersecret_internal_key_123` wins and every
  authenticated test 403s. Run with an explicit override in-container.

## Follow-up filed by this ticket

Merging `EvaluateSwarm` and `EvaluateHolisticSwarm` into one path. The case is
stronger after this work than before it: the two structs now carry
`KEEP IN SYNC` comments and a cross-path test, which is a mechanism for detecting
drift rather than a cure for it. GOA-133 will have to touch both again.
