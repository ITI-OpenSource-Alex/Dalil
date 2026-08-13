# GOA-134 — POST fault-injection matrix

Captured after the fix, same harness, same command:
`GOA_MATRIX_OUT=... go test ./agents/ -run TestHolisticMatrix -count=1`

Compare with `GOA-134-pre-matrix.md`.

### Provider error

| Completed criteria | `overall_band` key | value | `status` | `partial` | `completed_count` |
|---|---|---|---|---|---|
| 4 of 4 | **present** | 7 | completed | false | 4 |
| 3 of 4 | **present** | 7 | completed | true | 3 |
| 2 of 4 | absent | — | completed | true | 2 |
| 1 of 4 | absent | — | completed | true | 1 |
| 0 of 4 | absent | — | failed | false | 0 |

### Malformed JSON (BUG-057 shape)

| Completed criteria | `overall_band` key | value | `status` | `partial` | `completed_count` |
|---|---|---|---|---|---|
| 4 of 4 | **present** | 7 | completed | false | 4 |
| 3 of 4 | **present** | 7 | completed | true | 3 |
| 2 of 4 | absent | — | completed | true | 2 |
| 1 of 4 | absent | — | completed | true | 1 |
| 0 of 4 | absent | — | failed | false | 0 |

### Deadline exceeded

| Completed criteria | `overall_band` key | value | `status` | `partial` | `completed_count` |
|---|---|---|---|---|---|
| 4 of 4 | **present** | 7 | completed | false | 4 |
| 3 of 4 | **present** | 7 | completed | true | 3 |
| 2 of 4 | absent | — | completed | true | 2 |
| 1 of 4 | absent | — | completed | true | 1 |
| 0 of 4 | absent | — | failed | false | 0 |
