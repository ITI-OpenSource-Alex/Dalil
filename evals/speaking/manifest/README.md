# Speaking evaluation dataset — source governance

SPEAK-EVAL-004. Every speaking evaluation item is declared in `manifest.json`
before it can be used, and the declaration is what decides whether it may
contribute to a number capable of blocking a release.

```bash
python evals/speaking/manifest/validate.py
```

Exit 0 means the gating splits are safe to publish from.

## Why a manifest rather than a folder

The alternative is a directory of audio and a spreadsheet. That arrangement
makes three questions unanswerable at the exact moment they matter — when a
number is about to be published:

- *Is this item licensed?* A file on disk carries no permission record.
- *Who assigned this band?* A band with no named rater is an opinion of unknown
  provenance, and the accuracy claim built on it inherits that.
- *Is this the same speaker as that item?* Without an explicit candidate id,
  the same voice can land on both sides of a comparison and inflate it silently.

The manifest answers all three by construction, and `validate.py` refuses the
answers that are not good enough.

## Current state

All 20 existing speaking rows are **quarantined**. They are model-written
transcripts with model-assigned bands and no audio. They exercise the plumbing;
they cannot support an accuracy claim, because a number computed over them
measures agreement with a model rather than accuracy. `run_speaking_eval`
reports the counts rather than a score, and says why.

Zero items are currently cleared to gate. That is the honest state, not a
failure.

## The four rules

| Rule | What it enforces |
|---|---|
| `gating` | An item in a gating split is permitted, human-validated, banded, and hashed. |
| `leakage` | A `candidate_id` or `series_id` appears in at most one split. |
| `governance` | An approved source names its basis, its reference, and its reviewer. |
| `restricted-media` | Restricted audio is never in the repo, and no audio file sits in the tree undeclared. |

`series_id` deserves a note. Candidate leakage is the obvious one. Series
leakage is quieter and just as damaging: one recording shares an examiner, a
microphone and an editing pass, so a system evaluated on one answer from it has
already seen the conditions of every other answer in it.

## Workflows

### Permission review

Before an item is added:

1. Establish the basis — a licence, written permission, or a reason none is
   needed. Record it in `permission.basis` in full sentences, not a keyword.
2. Record who reviewed it and when. `permission.status: "granted"` requires
   `reviewed_by`; the validator enforces this.
3. Link the decision: `governance_ref` points at the ticket or document.

`status: "unknown"` is the default and is **not** a synonym for
`"not_required"`. An item nobody has reviewed is not a permitted item. Getting
this backwards is how an unreviewed recording reaches a published result.

### Rating and adjudication

Official band labels are preferred. Where none exist:

1. Two named raters band the item independently. Both go in `labels.raters`.
2. Where they agree within half a band, take the mean.
3. Where they disagree by more, a third rater adjudicates and
   `labels.adjudicated` is set true.
4. `labels.source` becomes `commissioned_double_rated`. A single rater does not
   satisfy this and the validator rejects it.

Commissioned rating is **not** in the 004-lite scope actually built — no raters
have been engaged. The workflow is specified and enforced so that the day an
item arrives with two raters, the manifest already knows what to require.

### Splits

- `quarantine` — items that exist but must not influence any published number.
- `dev` — non-gating on purpose, so that tuning against it cannot become tuning
  against the gate.
- `smoke` — the small authorised set CI runs.
- `test` — held out; read for a release decision, never for iteration.

Assign by `candidate_id` and `series_id`, never per item. The validator will
reject a split that separates them, but it is easier to get right the first
time.

### Retention and deletion

`retention.policy` is one of `indefinite`, `delete_by_date` (with
`delete_after`), or `delete_on_request`. A deletion is recorded by setting
`deletion_ref` and removing the media, not by deleting the manifest entry —
the entry is the record that the item once existed and is now gone.

## Adding an authorised item

1. Add the entry with `split: "quarantine"`.
2. Complete `permission`, `source`, `labels` and `retention`.
3. Store audio externally. If it must live in the repo, it must be
   unrestricted, path-declared, and hashed.
4. Run `validate.py`. It will refuse the item for any gating split until it
   qualifies.
5. Only then move it to `smoke` or `test`, and run `validate.py` again.

Step 5 is the one that matters: the manifest is designed so that promoting an
item is a deliberate act that has to survive the validator, rather than a
default that happens because nobody stopped it.
