# Speaking evaluation — tri-language conformance harness

SPEAK-EVAL-003 acceptance criterion: *shared fixtures decode in all three
languages*.

"Decode" is the easy half. Three decoders can each accept the same bytes and
still disagree about what they mean — one treats an absent band as `0`, another
as `null`, a third refuses to build the object at all; one rounds `6.375` up,
another to nearest-even. Each looks correct in its own test suite. That is
exactly the drift this contract replaces, so proving the three *parse* the
fixtures would prove nothing worth having.

So each implementation emits a **digest**: a normalised, line-oriented
projection of what it believes the fixture says, including values it had to
*recompute* rather than echo. The driver runs all three and diffs the digests.
A single differing line fails the run and names the field.

## Running it

```bash
python packages/contracts/conformance/run_conformance.py
```

Requires Go, Python (pydantic v2) and Node on PATH. No network access. The
TypeScript emitter is compiled with the repo's local `typescript` from
`packages/contracts/ts/node_modules`.

## What is in the digest

Ordering is document order for criteria (array order is semantic — a UI renders
them in it) and sorted for sets that have no meaningful order. Every float is
rendered `%.4f`, so `6.5` and `6.50` cannot masquerade as a difference and a
genuine `6.3750` mean is visible.

Three classes of line:

| Prefix | What it proves |
|---|---|
| `criterion[i].*`, `overall.*`, `provenance.*` | The decoders agree on what was *stated*. |
| `derived.*` | The decoders agree on what *follows* — the mean of the scored bands and the half-band rounding are recomputed from the decoded values by each language's own arithmetic, not copied from the fixture. |
| `verdict`, `validation_problems` | The decoders agree on whether the payload is *acceptable*. |

The distinction that matters most is `absent` versus `0.0000`. An absent band
prints the literal `absent`; a band of zero prints `0.0000`. If any
implementation ever collapses the two, the digest line changes and the run
fails. That is BUG-055 wired to a test rather than to a code review.

## Invalid fixtures, and why they are tiered

`packages/contracts/fixtures/speaking-evaluation/invalid/` holds one fixture per
defect. Not every defect is visible to every implementation, and pretending
otherwise would mean either weakening the check or writing a test that lies.

**Tier 1 — all three must reject.** Defects visible from the payload alone:
missing required fields, a band that is not a half step, a scored criterion with
no band, an unavailable criterion carrying one, a transcript span with no
offsets, an overclaimed `score_semantics`.

**Tier 2 — schema and Go only.** Defects that need the frozen rubric to detect,
currently `invented-descriptor-id`. The rubric lives in
`services/speaking/internal/contract/rubric.go` because the scorer that must
cite it is Go. Python and TypeScript are consumers; they receive a descriptor id
that has already been validated at the point of production and have no basis to
re-check it. Making them re-check would mean shipping a second copy of the
rubric, and two copies of a rubric is how a rubric silently forks.

Where a defect is caught differs by design — the JSON Schema catches shape, Go
and Python reject at decode, TypeScript reports at validate. The digest records
only `verdict=rejected`, because *where* it was caught is an implementation
detail and *whether* it was caught is the contract.
