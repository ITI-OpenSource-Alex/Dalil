# FAQ matching: threshold calibration (GOA-045)

GOA-045 asks to "empirically verify the 0.85 similarity threshold against real
paraphrases". This is that measurement, run against the real seeded table in
Postgres with `pg_trgm`.

**Headline: 0.85 was never the problem. The matching function was.**

## The bug the calibration found

The original code matched with `similarity(question_pattern, question)`.

`similarity()` is symmetric — shared trigrams divided by the union of both
strings' trigrams — so a short user question scored against a longer curated
pattern is penalised for every word it did not say. The ticket's own canonical
example is the clearest case:

| Query | Pattern | `similarity()` | `word_similarity()` |
|---|---|---|---|
| `how do I register for IELTS` | `How do I register for the IELTS exam in Egypt?` | **0.628** | **0.871** |

GOA-045's definition of done says that pair must score **>0.85**. Under
`similarity()` it scores 0.63, so the documented threshold could never have
matched it — the FAQ path was reaching almost nothing, and the metric that
would have shown this (`goa_faq_hits_total`) did not exist yet.

`word_similarity(query, pattern)` asks the question the FAQ actually wants: is
the user's question a good match for some *contiguous run of words inside* the
pattern? That is exactly the "user says less than the canonical question"
shape, and it puts the canonical example at 0.871 — above the documented 0.85,
as originally specified.

## Threshold selection

Measured against the 30 seeded entries plus their 88 aliases. `best` is the
highest score across canonical patterns and aliases.

### One-way `word_similarity(query, pattern)` — **chosen**

| Should hit | Query | best |
|---|---|---|
| ✅ | `what is remonstration` | 1.000 |
| ✅ | `what is uni-assist` | 1.000 |
| ✅ | `what is a Studienkolleg` | 1.000 |
| ✅ | `do they keep my passport` | 1.000 |
| ✅ | `how do I book a visa appointment` | 1.000 |
| ✅ | `does the APS certificate expire` | 1.000 |
| ✅ | `Whats a studienkolleg?` | 1.000 |
| ✅ | `how do I register for IELTS` | 1.000 |
| ✅ | `How do I sign up for the IELTS test?` | 0.765 ← misses |
| ❌ | `What is the capital of Germany?` | 0.387 |
| ❌ | `How much does a car cost in Berlin?` | 0.364 |
| ❌ | `Which university should I choose for CS?` | 0.311 |
| ❌ | `What scholarships can I apply for?` | 0.289 |
| ❌ | `Tell me about the weather in Cairo` | 0.280 |

**Zero false positives, with the nearest one at 0.387 — a 0.46 margin below the
threshold.** One paraphrase misses.

### Bidirectional `GREATEST(word_similarity(q,p), word_similarity(p,q))` — rejected

| Should hit | Query | one-way | bidirectional |
|---|---|---|---|
| ✅ | `Can you tell me what uni-assist is please?` | 0.452 | 1.000 |
| ✅ | `How do I sign up for the IELTS test?` | 0.765 | 0.867 |
| ❌ | `What is the capital of Germany?` | 0.387 | **0.750** |
| ❌ | `How do I register my car in Germany?` | 0.514 | **0.667** |

Bidirectional recovers both missed paraphrases. It also drags an unrelated
question — *"What is the capital of Germany?"* — from 0.387 to 0.750, leaving
only a 0.10 margin below the threshold.

**Rejected, because the two failure modes are not equally bad.** A false
negative costs one LLM call and still produces a correct, cited answer. A false
positive serves a confidently wrong curated answer, instantly and with no
citation the user would think to question. A 0.10 margin on a feature whose
entire risk is *confidently wrong* is not worth two extra paraphrases.

## The near-miss that set the final threshold

`word_similarity` scores the best **contiguous extent** of the pattern. That is
what makes it right for "user said less than the canonical question" — and it
is also a specific hazard on this corpus, because a question sharing a long
prefix scores high even when the one word that changes the answer differs.

An existing test in `test_visa_integration.py` caught a live instance:

| Query | Matched entry | score |
|---|---|---|
| `...Thanaweya Amma certificate recognized for university admission in **France**?` | `...for university admission in **Germany**?` | **0.862** |

At a 0.85 threshold that question is answered with **German** requirements —
confidently, instantly, with a German citation attached. `strict_word_similarity`
scores it identically (0.862), so switching function does not help.

The entries most exposed to this are the ones users can least afford to get
wrong: country names, IELTS Academic vs General, public vs private insurance —
entries that differ by a single decisive token.

**Threshold raised to 0.90.** With aliases carrying recall, every genuine match
in the calibration set lands at 1.000, so the gate's only remaining job is
rejecting near-misses:

| | score |
|---|---|
| all true positives (canonical or alias) | 1.000 |
| worst false positive (`...in France?`) | 0.862 |
| next worst (`How do I register my car in Germany?`) | 0.514 |

GOA-045's DoD is still satisfied — it requires *"how do I register for IELTS"*
to score **>0.85**, and it scores **1.000**.

## How recall is recovered instead

Aliases, which GOA-045's acceptance criteria already call for. `Whats a
studienkolleg?` scores 0.769 against the canonical wording and 1.000 once
`whats a studienkolleg` is an alias.

This is deliberately the *manual* lever. A human decides that two phrasings mean
the same question; lowering the threshold makes that decision statistically, for
every entry at once, with no review. When a real query misses, add an alias —
`goa_faq_hits_total` against total query volume is how you find them.

## Reproducing

Requires the seeded table (migration 028):

```sql
WITH probes(q, should_hit) AS (VALUES
  ('how do I register for IELTS', true),
  ('What is the capital of Germany?', false)
)
SELECT p.should_hit, p.q,
  round(max(GREATEST(
    word_similarity(p.q, f.question_pattern),
    COALESCE((SELECT MAX(word_similarity(p.q, a)) FROM unnest(f.aliases) a), 0)
  ))::numeric, 3) AS best
FROM probes p CROSS JOIN faq_entries f
GROUP BY p.should_hit, p.q ORDER BY best DESC;
```

## Revisit when

- `goa_faq_hits_total` stays flat while query volume grows — coverage or
  phrasing gap; add aliases before touching the threshold.
- `goa_faq_stale_suppressed_total` climbs — entries are aging out, which is the
  review backlog rather than a matching problem.
- The table reaches thousands of entries — the scan-based query should move to
  the `<%` operator so a trigram index can actually be used, and the margins
  above should be re-measured at that size.
