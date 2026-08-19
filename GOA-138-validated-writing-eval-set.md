# GOA-138 — Expand the examiner-validated writing evaluation set to 20

**Type:** Content / evaluation data

**Depends on:** GOA-028, GOA-136

**Priority:** P1 before any Gold Tier accuracy claim

## Problem

The published writing accuracy is based on only three officially banded essays. A
single verdict changes that headline by 33 percentage points. GOA-136 makes the
limitation impossible to hide, but engineering cannot turn synthetic labels into
validation.

## Scope

- Expand `evals/golden_dataset.json` from 3 to at least 20 writing rows with bands
  assigned by a named qualified human examiner or an openly licensed official source.
- Preserve `band_source`, `label_validated`, source URL/attribution, task type, exact
  word count, and examiner notes for every row.
- Cover Academic and General Training Task 2, a deliberate band spread, under-length
  responses, off-topic but fluent responses, and other criterion-asymmetric cases.
- Do not merge the existing 20 model-generated rows into the validated set. They stay
  under `writing_synthetic_unvalidated` with `label_validated: false`.
- Run the GOA-136 report after expansion and publish the new n, provenance, accuracy,
  MAE, judge-family delta, and self-consistency without relaxing the 80% floor.

## Copyright guidance carried over verbatim from GOA-028 Task 1

> [!WARNING]
> **Copyright.** Cambridge IELTS books are copyrighted. Store *your own* essays or openly-licensed samples with the official band descriptors as the rubric, and cite the descriptor source rather than reproducing book content. If in doubt, write the essays yourself and band them against the public descriptors — that is defensible and yours to publish.

## Acceptance criteria

- At least 20 rows have `label_validated: true` and non-empty `band_source`.
- Every validated source is reviewable and legally usable in the repository.
- No synthetic or model-generated band appears in the validated denominator.
- No single band value exceeds 40% of the set.
- The GOA-136 container suite and real report flow are rerun and their artefacts name
  the new dataset size and sources.
