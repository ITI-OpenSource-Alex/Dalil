# GOA-028 — Implementation Plan: LLM-as-a-Judge evaluation pipeline

**Ticket:** [GOA-028](GOA_Sprint_3_Tickets.md#goa-028--llm-as-a-judge-evaluation-pipeline--writing-and-speaking-accuracy-scoring) · P1 · 3 pts · QA · **Pattern: NEW**
**Depends on:** GOA-013 (speaking swarm) · GOA-014 (writing swarm) · GOA-020 (eval suite skeleton — *exists*) · GOA-130 (budget telemetry)

> **This is the Gold Tier requirement.** It is the ticket that turns "our agents grade essays" into "our agents grade essays and here is the measured accuracy against IELTS descriptors." Treat the number it produces as something you will defend in a viva.

---

# How this plan is used — skeleton-mentor contract

This is a **NEW pattern**, so the full workflow applies ([skeleton-mentor](../GOA/.agents/skills/skeleton-mentor/SKILL.md)):

| Phase | Owner | Scope in this ticket |
|---|---|---|
| 1 SPEC | agent | this document |
| **2 FIRST PASS** | **developer** | **Tasks 1, 2, 4** — the judge prompt, the verdict parser, the accuracy maths |
| 3 FINISH | agent | edge cases and fixes *in the developer's code*, explained |
| 4 TESTS | agent | every test below — written, run, iterated to green |
| 5 REPORT | agent | real executed counts, honest mock-vs-reality split |

**ag: do not implement Tasks 1, 2 or 4.** Output the skeleton and stop. Tasks 3, 5, 6, 7 are REPEAT-shaped plumbing and are yours.

**Why these three are the developer's:** they are the only places where *judgement about IELTS* lives. The rest is I/O. If you write only three things in this ticket, these are the three that teach you what the eval actually measures.

---

# Part 0 — Verified starting state

Read before planning anything; several of the ticket's criteria are already partly built.

| What | State | Where |
|---|---|---|
| Eval runner with argparse, S3 upload, `--compare-with`, delta calc | **exists** | `evals/runner.py` (`main()` at :206, `_calc_delta` at :201) |
| Golden dataset | **exists but placeholder** | `evals/golden_dataset.json` — `rag`/`scoring`/`speaking`/`writing` keys, **writing n=5, speaking n=10**, contents are `"Dummy RAG question 1"` style stubs |
| Writing eval | **band-comparison only, no judge** | `run_writing_eval()` :177 — POSTs to `/essays/evaluate`, scores `abs(band - expected) <= 0.5` |
| Speaking eval | **stubbed out, returns `None`** | `run_speaking_eval()` :170 — deliberately skipped: *"Speaking is WS-only… to prevent testing a fabricated bare-LLM system instead of the actual 4-agent swarm"* |
| CI workflow with path filter | **exists** | `.github/workflows/evals.yml` — `paths: evals/**`, seeds DB, runs `pytest evals/tests/`, then `runner.py --compare-with s3://…` |
| Reports directory | **exists**, ~9 JSON reports | `evals/reports/` |

**Three consequences for scope:**

1. **The band-vs-expected comparison is not the judge.** It answers "did the agent land within 0.5 of the expert band" — a useful MAE signal, but not ACCURATE / OVERSCORED / UNDERSCORED with a reason. Both are required; keep the existing one as the MAE input and add the judge alongside it.
2. **The speaking stub's reasoning is correct and must be respected.** Do not replace it with a bare-LLM call to make a number appear. Either drive the real WebSocket swarm (Task 6) or report speaking as *not measured* — never a fabricated figure.
3. **The golden dataset is the long pole.** 20 essays + 20 transcripts with *expert* bands is the actual work; the pipeline around it is a day. See Task 1.

---

# Task 1 — Golden dataset — **DEVELOPER FIRST PASS**

> The pipeline is worthless if the labels are. This is the task that decides whether the accuracy number means anything.

**File:** `evals/golden_dataset.json`

### Steps

1. Replace the 5 dummy writing entries with **20 real IELTS Task 2 essays**, each with:
   ```json
   {
     "id": "w-01",
     "essay": "<full essay text>",
     "task_type": "task2",
     "expected_band": 6.5,
     "expected_criteria": {"task_response": 6.5, "coherence": 6.0, "lexical": 7.0, "grammar": 6.5},
     "band_source": "Cambridge IELTS 15 Test 2 sample answer, examiner commentary p.148",
     "notes": "Band 6.5 overall; examiner flags limited range of linking devices"
   }
   ```
2. Same for **20 speaking transcripts** under `speaking`.
3. **`band_source` is mandatory on every row.** A band with no provenance is an opinion, and the eval's entire claim is that it measures against *official* descriptors.
4. Spread the bands deliberately: aim for roughly 4 rows each at bands 5.0–5.5, 6.0, 6.5, 7.0, 7.5+. A dataset clustered at 6.5 makes a mediocre grader look accurate.
5. Include at least **2 deliberately hard cases** per domain — e.g. an off-topic but fluent essay (high lexical, low task response), and a short-but-precise answer. These are where OVERSCORED/UNDERSCORED verdicts earn their keep.

> [!WARNING]
> **Copyright.** Cambridge IELTS books are copyrighted. Store *your own* essays or openly-licensed samples with the official band descriptors as the rubric, and cite the descriptor source rather than reproducing book content. If in doubt, write the essays yourself and band them against the public descriptors — that is defensible and yours to publish.

**Blocked by GOA-049?** No. GOA-049's Cambridge content is for the *exam* engine. This dataset is for evaluation and is independent — do not wait on it.

### Tests (ag)
1. `test_golden_dataset_shape` — every writing/speaking row has `id`, text, `expected_band`, `expected_criteria`, `band_source`; ids unique.
2. `test_golden_dataset_size` — ≥20 rows per domain (the ticket's number).
3. `test_band_distribution_is_spread` — no single band value is more than 40% of rows.
4. `test_no_placeholder_rows` — the string `"Dummy"` appears nowhere.

---

# Task 2 — The judge — **DEVELOPER FIRST PASS**

**New file:** `evals/judge.py`

### Behaviour tasks (not fill-in-the-blanks)

1. **`build_judge_prompt(domain, text, agent_evaluation, rubric) -> str`**
   - Must include the **official IELTS band descriptors** for each of the four criteria in that domain. Store them in `evals/rubrics/writing_task2.md` and `evals/rubrics/speaking.md` and load them — do not inline a paraphrase, and do not rely on the model's memory of the descriptors. Same discipline as GOA-108: the rubric is fetched context, not recall.
   - Must show the agent's per-criterion bands **and** its justification text.
   - Must demand exactly one verdict from `ACCURATE | OVERSCORED | UNDERSCORED` plus a reason quoting the descriptor language it relied on.
   - Must instruct: judge against the descriptors, not against your own preferred band.

2. **`judge_evaluation(domain, item, agent_result) -> JudgeVerdict`**
   - Returns a typed result: `verdict`, `reason`, `judged_band`, `per_criterion_verdicts`.
   - **Strict JSON output.** The response must parse without prose. See the trap below.

3. **Verdict rule** — implement the ticket's definition exactly: agent band within **0.5** of expert band ⇒ `ACCURATE`; above ⇒ `OVERSCORED`; below ⇒ `UNDERSCORED`. The judge supplies the *reason*; the arithmetic is yours, in code, not the model's. Never let the model decide the verdict label directly — it will drift.

> [!CAUTION]
> **Traps this project has already hit — you will hit them here too.**
> - **Thinking blocks.** `claude-opus-4-8` sometimes returns a `ThinkingBlock` before the text block. `response.content[0].text` raises `'ThinkingBlock' object has no attribute 'text'`. Iterate the blocks and take the first with text (see `rag_service._invoke_via_sdk`).
> - **Prose instead of JSON on retry.** Appending only the validation error made the model reply *"I don't have what I'd need to produce this correction."* If you retry, the retry prompt must re-state "output ONLY the JSON object".
> - **Gateway tail latency is erratic** — 2.5 s to 110 s for identical calls. Set an explicit timeout and retry once.
> - **`content-blocked`.** AgentRouter refused a legitimate government page during GOA-109. If an essay trips it, record the failure; do not silently score it.

### Tests (ag)
1. `test_judge_prompt_contains_official_descriptors` — the loaded rubric text appears in the prompt.
2. `test_judge_prompt_includes_agent_bands_and_justification`.
3. `test_verdict_is_computed_in_code_not_taken_from_model` — feed a model response claiming ACCURATE while bands differ by 1.5; assert the code returns OVERSCORED.
4. `test_within_half_band_is_accurate` — boundary cases at exactly 0.5 and 0.51.
5. `test_thinking_block_response_parsed` — mock a response whose first block has no `.text`.
6. `test_non_json_response_retried_then_recorded_as_failure`.
7. **All of these mock the LLM.** Zero live calls in the default suite — the cassette lesson from the AgentRouter migration applies.

---

# Task 3 — Wire the judge into the runner — **ag**

**File:** `evals/runner.py`

1. Extend `run_writing_eval()` to call the judge per item **in addition to** the existing band comparison. Keep both: the band delta feeds MAE, the judge feeds accuracy.
2. Add `mean_absolute_error` per criterion to the returned dict (ticket requirement).
3. Emit per-item rows so the HTML report can show a breakdown: `id`, agent bands, expert bands, verdict, reason, delta.
4. Preserve the existing isolation pattern — one item's failure must not abort the run.
5. Add `--domains writing,speaking` so a run can be scoped (and so the developer can iterate on writing alone without paying for speaking).

### Tests (ag)
1. `test_runner_reports_accuracy_and_mae_per_criterion`.
2. `test_single_item_failure_does_not_abort_run`.
3. `test_domains_flag_scopes_the_run`.

---

# Task 4 — Accuracy, MAE and the regression gate — **DEVELOPER FIRST PASS**

**File:** `evals/runner.py` (`_calc_delta` exists at :201 — extend, don't rewrite)

### Behaviour tasks
1. `accuracy(domain) = ACCURATE verdicts / judged items`. Items that errored are **excluded from the denominator and reported separately** — never counted as accurate, never silently dropped.
2. `mean_absolute_error(criterion) = mean(|agent_band − expert_band|)`.
3. **Regression gate:** fetch the previous report (already implemented at :73), compute per-domain delta, exit **1** if any domain drops **>5 percentage points**, or if accuracy is below the **80%** floor.
4. Distinguish the two failure modes in the exit message — "below floor" and "regressed vs previous" are different problems with different fixes.

### Tests (ag)
1. `test_accuracy_excludes_errored_items_from_denominator`.
2. `test_mae_per_criterion`.
3. `test_gate_fails_below_80_percent`.
4. `test_gate_fails_on_more_than_5_point_drop` (79% after 85% fails; 84% after 85% passes).
5. `test_gate_passes_on_first_ever_run` — no previous report must not crash or fail the build.

---

# Task 5 — HTML report — **ag**

**New:** `evals/templates/report.html.j2`, rendered by the runner.

Sections: header (run id, commit, timestamp, models used) · **overall accuracy per domain vs 80% target, pass/fail badge** · per-criterion MAE table · per-item breakdown (essay id, agent bands, expert bands, verdict, reason) · delta vs previous run.

### Tests (ag)
1. `test_report_renders_all_sections`.
2. `test_report_shows_failing_badge_when_below_target`.
3. `test_report_handles_missing_previous_run`.
4. `test_report_marks_unmeasured_domain_explicitly` — speaking, if not implemented, must read **"not measured"**, never 0% and never omitted.

---

# Task 6 — Speaking: real swarm or honestly unmeasured — **ag**

The current stub is right to refuse a fake number. Two acceptable outcomes, in preference order:

**(a) Drive the real WebSocket swarm.** Add `evals/ws_client.py` that connects to the speaking service, replays a transcript as text (the exam path takes text — no audio needed), and waits for the `evaluation` event. This is the honest implementation and is the same path GOA-127 leaves working without a speech sidecar.

**(b) Report speaking as not measured.** Keep the stub, make the report and the PR comment say so explicitly, and note it as a limitation in GOA-040.

**Do not** call the writing endpoint with a transcript, or call a bare LLM, to produce a speaking number.

### Tests (ag)
1. `test_ws_client_replays_transcript_and_captures_evaluation` (mocked WS).
2. `test_speaking_absent_is_reported_not_zero`.

---

# Task 7 — CI, Langfuse annotation, Prometheus — **ag**

1. **`.github/workflows/evals.yml`** — the path filter (`evals/**`) already exists; **keep it**. Add the PR comment: domain, accuracy, target, delta, badge. Budget: ~$1.50–2.00 per full run against a fixed $150 quota, so **do not remove the filter** and do not add a schedule.
2. **Langfuse annotation** — attach the verdict to the *original agent trace* so an eval result links to the call that produced the band. Requires the agent run to expose its trace id to the eval.
3. **Prometheus** — `goa_eval_judge_accuracy` gauge, labels `domain`, `criterion`.

### Tests (ag)
1. `test_pr_comment_body_contains_domain_accuracy_target_delta_badge`.
2. `test_prometheus_gauge_labels`.
3. Manual: force a regression by flipping golden verdicts, confirm the PR comment shows a failing badge (the ticket's own DoD).

---

# Task 8 — `PROGRAM_FIT_WEIGHT` calibration — **DEVELOPER FIRST PASS (analysis), ag (harness)**

> Added to this ticket because it is the one place in the project with a measurement harness. **This is a tuning question that must be answered with data, not taste** — which is exactly what GOA-028 exists to enable.

**File:** `services/rag/app/services/soft_score.py`

**The problem.** `PROGRAM_FIT_WEIGHT = 0.35`, so **65% of every `/match` score is the candidate's absolute strength** — which is *constant for a given user across every program*. Only 35% reflects fit with the specific program. Ranking is therefore mostly driven by a term that cannot change the order.

Related constants, all currently unvalidated guesses: `COVERAGE_WEIGHT = 0.25`, `_FIT_SCALE = {"ielts": 1.5, "gpa": 1.0, "ects": 60, "work": 3}`.

**Why it is not obvious.** Raising the weight sharpens differentiation between programs but makes the score less comparable *across* users (a weak candidate at a perfectly-fitting program could outrank a strong candidate at a slightly-off one). Which is correct depends on what `/match`'s score is *for* — ranking within a user's list (favours high weight) or communicating admission odds (favours low). **Decide that first; the number follows.**

### Steps
1. **Developer:** write one paragraph in this file stating what the `/match` score means to a user. Everything else follows from it.
2. **ag:** add `evals/match_ranking_eval.py` — a golden set of ~10 `(profile, program, expected_rank_band)` triples labelled by the developer, scoring ranking quality (nDCG or simple rank correlation) at `PROGRAM_FIT_WEIGHT` ∈ {0.35, 0.5, 0.65, 0.8}.
3. **ag:** report the curve. **No LLM calls** — this is deterministic arithmetic, so it is free and can run on every PR.
4. **Developer:** pick the value; record the reasoning next to the constant.

### Tests (ag)
1. `test_ranking_eval_is_deterministic` — same input, same output, zero network.
2. `test_weight_sweep_covers_configured_values`.
3. `test_ranking_quality_metric_matches_hand_computed_example`.

---

# Definition of Done

- 20 essays + 20 transcripts, every row with `band_source`; no placeholder text.
- Judge returns ACCURATE / OVERSCORED / UNDERSCORED **with the verdict computed in code**, and a descriptor-grounded reason.
- Accuracy ≥80% per measured domain; errored items excluded from the denominator and reported.
- MAE per criterion in the report.
- Regression gate fails on a >5-point drop *and* on sub-80% absolute, with distinct messages.
- HTML report renders every section; speaking, if unmeasured, says so.
- CI posts the PR comment; the path filter is intact.
- **Default test suite makes zero live LLM calls.** A gated live run is opt-in.
- Full run completes in <5 minutes.
- `PROGRAM_FIT_WEIGHT` chosen from the sweep, with the reasoning recorded.

---

# Manual verification (developer)

```bash
python evals/runner.py --domains writing
```
**Expect:** a JSON report in `evals/reports/`, accuracy printed per domain, MAE per criterion, exit 0.

```bash
python evals/runner.py --domains writing --compare-with evals/reports/<previous>.json
```
**Expect:** a delta line per domain. Hand-edit the previous report to a higher accuracy and re-run — **expect exit 1** and a message naming the regression.

Then open the HTML report and read three per-item rows against the essays. **If a reason does not quote descriptor language, the judge prompt is not doing its job** — no accuracy percentage compensates for that.

> The number this pipeline produces is the one you will put in GOA-040 and defend in a viva. Two honest questions to answer in writing before you publish it: the judge and the evaluated agent are currently **the same model** (`claude-opus-4-8`) — judging with `gpt-5.5` instead costs little and removes the self-referential caveat; and 20 items per domain is a **small** sample, so state the figure with its n and avoid implying a precision it cannot carry.
