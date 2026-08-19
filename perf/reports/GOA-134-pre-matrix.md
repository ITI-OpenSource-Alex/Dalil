# GOA-134 — PRE fault-injection matrix

Captured **before any source edit**, at `git rev-parse --short HEAD` =
`996dedd` + the GOA-135 changes, via
`GOA_MATRIX_OUT=... go test ./agents/ -run TestHolisticMatrix -count=1`.

A deterministic mock is correct here and only here: the injected fault *is* the
subject. Assertions read the **serialised JSON**, not the Go struct — `omitempty`
behaviour is the contract a client sees.

## What this shows

`overall_band` is present at every failure level, including when **no criterion
completed at all**, where it reports **0** — BUG-055's exact shape, a score the
model never produced presented as a real one. `completed_count` does not exist,
so a client cannot tell 4-of-4 from 1-of-4 except via `partial`, a boolean no
consumer is required to read.

`services/exam/app/api/internal.py` then persists this value to
`exam_results.band_score` (`NOT NULL`) as the candidate's official IELTS speaking
band.


### Provider error

| Completed criteria | `overall_band` key | value | `status` | `partial` | `completed_count` |
|---|---|---|---|---|---|
| 4 of 4 | **present** | 7 | completed | false | absent |
| 3 of 4 | **present** | 7 | completed | true | absent |
| 2 of 4 | **present** | 7 | completed | true | absent |
| 1 of 4 | **present** | 7 | completed | true | absent |
| 0 of 4 | **present** | 0 | failed | false | absent |

### Malformed JSON (BUG-057 shape)

| Completed criteria | `overall_band` key | value | `status` | `partial` | `completed_count` |
|---|---|---|---|---|---|
| 4 of 4 | **present** | 7 | completed | false | absent |
| 3 of 4 | **present** | 7 | completed | true | absent |
| 2 of 4 | **present** | 7 | completed | true | absent |
| 1 of 4 | **present** | 7 | completed | true | absent |
| 0 of 4 | **present** | 0 | failed | false | absent |

### Deadline exceeded

| Completed criteria | `overall_band` key | value | `status` | `partial` | `completed_count` |
|---|---|---|---|---|---|
| 4 of 4 | **present** | 7 | completed | false | absent |
| 3 of 4 | **present** | 7 | completed | true | absent |
| 2 of 4 | **present** | 7 | completed | true | absent |
| 1 of 4 | **present** | 7 | completed | true | absent |
| 0 of 4 | **present** | 0 | failed | false | absent |

---

## Cross-path divergence

`TestSwarmAndHolisticAgreeOnBandContract` drives the identical fault matrix
through both `EvaluateSwarm` (streaming) and `EvaluateHolisticSwarm` (full exam):

```
0 of 4 completed: holistic overall_band present=true but streaming present=false
1 of 4 completed: holistic overall_band present=true but streaming present=false
2 of 4 completed: holistic overall_band present=true but streaming present=false
```

The streaming path is correct — `swarm.go:43` gates on `MinCriteriaForOverallBand`
and `swarm.go:79` makes the field a `*float64` with `omitempty`. The constant is
declared in the same package, three files away, and `holistic.go` never
references it.

**This test is the guard that would have caught the original divergence.**

