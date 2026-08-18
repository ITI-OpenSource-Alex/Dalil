# Writing OCR-to-band benchmark — 2026-08-18

## Scope

- Engine: production Writing evaluation path, `claude-opus-5`, four criterion
  agents per essay.
- Dataset: six Academic Task 2 candidate responses extracted directly from the
  existing IELTS 15–17 OCR, each anchored to a published examiner band.
- Task 1 was excluded because a fair Task Achievement score requires the source
  chart or diagram.
- Every request used a unique user/session identifier. All six responses report
  `from_cache: false`.
- This is an end-to-end **OCR-to-scoring** pilot. OCR substitutions and missing
  characters are part of the measured input and therefore part of the error.

## Results

| Sample | Examiner | Engine | Delta | Latency |
|---|---:|---:|---:|---:|
| IELTS 15, Test 1, Task 2 | 7.0 | 5.5 | -1.5 | 45.9 s |
| IELTS 16, Test 1, Task 2 | 6.0 | 6.0 | 0.0 | 45.5 s |
| IELTS 16, Test 2, Task 2 | 4.5 | 4.0 | -0.5 | 48.2 s |
| IELTS 16, Test 3, Task 2 | 7.0 | 5.5 | -1.5 | 40.2 s |
| IELTS 16, Test 4, Task 2 | 4.0 | 3.0 | -1.0 | 29.1 s |
| IELTS 17, Test 1, Task 2 | 6.5 | 6.0 | -0.5 | 208.9 s |

| Metric | Result |
|---|---:|
| Successfully scored | 6 / 6 |
| Exact agreement | 16.7% (1 / 6) |
| Within ±0.5 band | 50.0% (3 / 6) |
| Within ±1.0 band | 66.7% (4 / 6) |
| Mean absolute error | 0.83 band |
| RMSE | 1.00 band |
| Mean signed error | **-0.83 band** |
| Median request latency | 45.7 s |
| p95 / maximum latency | 208.9 s |
| Request failures | 0 |
| Cache hits | 0 |

With only six samples, the p95 is the slowest observation under nearest-rank
calculation. The final request retried provider calls and should be described as
a latency outlier, not as a stable percentile estimate.

## Interpretation

The engine completed the full four-agent workflow reliably, but this pilot does
not support an accuracy claim. It found a systematic downward calibration bias
on raw OCR (`-0.83` band on average), especially on the two published Band 7
responses. The next controlled experiment should score the same answers after a
documented OCR-normalisation pass, then repeat each condition to separate OCR
error, grader calibration, and model variance.

## Slide-safe wording

> In a six-response OCR-to-scoring pilot using examiner-banded Cambridge Task 2
> answers, the four-agent engine completed 6/6 evaluations with 0.83-band MAE and
> 50% agreement within ±0.5 band. The evaluation exposed a -0.83-band downward
> bias and one provider-retry latency outlier, defining the next calibration and
> OCR-normalisation work.

Raw machine-readable evidence is in `GOA-writing-OCR-20260818.json`; the
reproducible harness is `perf/writing_ocr_benchmark.py`.
