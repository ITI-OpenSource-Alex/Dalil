# GOA-139 — benchmark structured programme-entity metadata for RAG

## Why this follow-up exists

GOA-137's frozen-corpus POST showed that the existing `category` filter is correct
but not selective enough for the adversarial programme-name queries. Both filtered
and unfiltered hybrid arms scored entity Recall@10 0.80, and the lexical arm appeared
in only 3% of entity top-k results.

The missed entity items turn on exact programme names/acronyms inside otherwise
generic `universities` documents. Every such document currently has the title
`MastersPortal Program Listing`; the actual programme name is embedded in the first
content line and cannot be used as a structured predicate.

## Proposed measurement

Evaluate a nullable `programme_name` (or canonical `programme_id`) document metadata
field populated deterministically from the ingested programme record. Do not add it
to production based on intuition alone.

1. Backfill a disposable copy of the frozen GOA-137 corpus from the source record or
   first-line parser, recording parse failures as null.
2. Add exact/normalised programme-name filtering as a separate benchmark arm.
3. Reuse the GOA-137 entity labels and report Recall@5/10, false-refusal rate and p95.
4. Only promote the column if it improves entity Recall@10 without violating the
   existing refusal or latency gates.

`target_country`, `field` and `deadline` remain unimplemented promises in the older
scraping strategy; this ticket does not assume they exist and does not use model
memory as metadata evidence.
