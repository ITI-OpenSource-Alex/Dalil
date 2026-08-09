# SPEAK-EVAL-007 — Scorer vs examiner bands

**Exploratory, non-gating.** Speaker roles were assigned by heuristic, not by a
second reviewer; reference bands are the channel owner's stated assessment (a
certified examiner), not a published per-criterion breakdown. Plan section 6.3
permits a report of this kind and forbids treating it as a release gate.

Source transcripts are not reproduced. They are third-party material held
locally under the permission recorded in the dataset manifest. What appears
below is our scorer's own output, plus band numbers, which are facts.

## 1. Headline

| lane | exercises | n | MAE | bias |
|---|---|---|---|---|
| text | prompt, rubric, swarm, aggregation | 7 | 1.000 | −1.000 |
| **audio** | **+ STT, prosody, intelligibility** | **3** | **0.667** | **−0.667** |

Two findings dominate.

**The scorer ranks well and scores low.** Spearman 0.860: it orders candidates
correctly and places the whole scale below the examiner. A systematic offset is
the most tractable failure mode available — far better than random error.

**Prosody is worth more than any prompt change made so far.** Every text-lane
number was produced with Fluency judging flow from text carrying no timing, and
Pronunciation abstaining entirely. Supplying real measurements cut MAE from
1.000 to 0.667 on the same items.

## 2. Per item

| item | examiner | text | audio | audio error |
|---|---|---|---|---|
| `yt-666eP6xBhzI` | 6.5 | 6 | 6.5 | +0.0 |
| `yt-OicvdCp5wrM` | 6.5 | 6.5 | — | — |
| `yt-ZDv9njERj0s` | 8.0 | 7 | 7.5 | -0.5 |
| `yt-lvF8q44170Q` | 8.5 | 7 | — | — |
| `yt-GKr5n9aa2Zw` | 8.5 | — | — | — |
| `yt-IevmdO16GuE` | 9.0 | 7 | 7.5 | -1.5 |
| `yt-gfKS-p7thDU` | 9.0 | — | — | — |

Dashes are items where fewer than three criteria completed, so no overall band
was published. That is the BUG-040 threshold working, not a missing number.
The audio lane was run on three items only; the remaining four have clips but
were not put through the sidecar.

## 3. Per criterion — the material for prompt iteration

Audio lane where available, text lane otherwise.

### `yt-666eP6xBhzI` — examiner 6.5, ours 6.5 (audio lane)

- **FC 7** — The measured features show genuinely fluent delivery: 157 words per minute (articulation 165 wpm) is at the top of the natural range, only 4 pauses reached 1 second (longest 1.4s), and just 5% of total time was spent paused. This is speech produced [...]
- **LR 6** — You have a wide enough vocabulary to discuss a range of topics at length and make your meaning clear, and you paraphrase successfully (e.g. describing Mumbai as the 'city of dream' with 'sea view' and 'street food'). You attempt some less common, topic- [...]
- **GRA 6** — You use a genuine mix of simple and complex structures, attempting relative clauses ('facilities which are very nice'), conditionals ('if your team member is stuck...'), and a variety of subordinate clauses with 'because', 'when' and 'if'. This range [...]
- **PR 7** — Recognition confidence is high (mean 0.91), indicating speech that was generally intelligible; however, 5% of words fell below 0.5 confidence, pointing to occasional dips in clarity rather than consistent ease of understanding. Chunking and phrasing are [...]

### `yt-OicvdCp5wrM` — examiner 6.5, ours 6.5 (text lane)

- **FC 6.5** — Note: no MEASURED SPEECH FEATURES (words per minute, articulation rate, pause counts/durations) were supplied with this transcript, so rate of speech, flow and hesitation cannot be judged. My assessment therefore covers only coherence and cohesion. On [...]
- **LR 6.5** — You have a wide enough vocabulary to discuss a variety of topics at length and make your meaning clear, and you paraphrase successfully throughout (e.g. explaining nationality/background when you couldn't find a single term). You reach into less common [...]
- **GRA 6** — You use a good mix of simple and complex structures, including conditionals, subordinate clauses and gerund phrases, and you produce a number of error-free sentences. However, errors are frequent and appear even in basic structures: article omissions, [...]
- **PR unavailable** — insufficient_evidence

### `yt-ZDv9njERj0s` — examiner 8.0, ours 7.5 (audio lane)

- **FC 8** — Your measured delivery is very fluent and confident: you speak at 177 words per minute (articulation rate 190 wpm), spend only 7% of the time paused, and have just five pauses over one second with the longest at 1.6s. This shows you speak at length [...]
- **LR 7** — You demonstrate a wide vocabulary that allows you to discuss a variety of topics—from data analytics to social status and cultural traditions—flexibly and at length. You use some less common and idiomatic vocabulary effectively, showing good awareness of [...]
- **GRA 7** — You use a genuine range of complex structures with good flexibility, including conditionals, relative clauses, passives, causatives ('I get them specifically made'), comparatives and noun clauses, and you frequently produce error-free sentences across [...]
- **PR 7** — Recognition confidence is fairly high (mean 0.89), indicating speech that was generally intelligible, but 7% of words fell below 0.5 confidence, so a noticeable minority of words were harder to decode and clarity dips at times. Phrasing is a clear [...]

### `yt-lvF8q44170Q` — examiner 8.5, ours 7 (text lane)

- **FC 7** — No measured speech features were supplied, so I cannot assess your rate of speech, flow, or hesitation from the audio; the following judgement is based only on coherence and cohesion from the transcript. Your ideas are consistently relevant and well [...]
- **LR 7** — You use vocabulary flexibly across a wide variety of topics (technology, cinema, housing, family values) and demonstrate good awareness of collocation and less common, topic-specific vocabulary, particularly when describing the house ('floor to ceiling [...]
- **GRA 6.5** — You use a good range of complex structures with some flexibility—conditionals ('if you're living in a house, the chances are you would have a backyard'), subordinate clauses ('As soon as I wake up, I have to check my phone'), and relative clauses—and you [...]
- **PR unavailable** — insufficient_evidence

### `yt-GKr5n9aa2Zw` — examiner 8.5, ours — (text lane)

- **FC 7** — No measured speech features (words per minute, pause counts and durations) were supplied, so I cannot judge your rate of speech, flow or hesitation from the audio; this assessment is based on coherence and cohesion only. On those grounds you perform at a [...]
- **LR 7.5** — You use a wide vocabulary readily and flexibly across a range of topics (work, travel, celebrations, apps, reviews), and you deploy idiomatic and colloquial language frequently and often skilfully ('on your toes', 'it just gets to you', 'I kid you not', [...]
- **GRA unavailable** — invalid_output
- **PR unavailable** — insufficient_evidence

### `yt-IevmdO16GuE` — examiner 9.0, ours 7.5 (audio lane)

- **FC 8** — Your delivery is genuinely fluent: the measured features show 172 words per minute (articulation rate 181 wpm), which is at the upper end of natural pace, with only 35 short pauses, none reaching 1 second, and just 5% of total time paused. This indicates [...]
- **LR 7** — You demonstrate a wide vocabulary that allows you to discuss a variety of topics (nature, weather, documentaries, advertising) at length and with fluency. You use some less common and idiomatic vocabulary effectively, such as 'handpick locations', 'make [...]
- **GRA 7** — You use a genuine range of complex structures with some flexibility, including relative clauses, subordinate clauses of reason and time, and effective concessive constructions ('no matter where you come from...'). You frequently produce error-free [...]
- **PR 7.5** — Recognition confidence is high (mean 0.95, with only 2% of words below 0.5), indicating speech that was consistently easy to decode across the full sample. Chunking and phrasing are even and well-controlled: 35 pauses of 0.3s or longer spread over more [...]

### `yt-gfKS-p7thDU` — examiner 9.0, ours — (text lane)

- **FC 7.5** — Note: No measured speech features (words per minute, articulation rate, pause data) were supplied, so rate of speech, flow and hesitation cannot be judged from the audio. This assessment therefore covers the coherence and cohesion components only. On [...]
- **LR 8** — You demonstrate a wide and flexible vocabulary resource that allows you to convey precise meaning across a range of topics (celebrities, fashion, food, and cooking as a profession). You use less common and idiomatic vocabulary skilfully and [...]
- **GRA unavailable** — provider_error
- **PR unavailable** — insufficient_evidence

## 4. What to change next

1. **Run the audio lane on the remaining four items.** n=3 is too few to act on,
   and the clips already exist. This is the cheapest next measurement.
2. **The residual is concentrated at the top.** Both band-6.5 items now land
   within half a band; the 9.0s sit at 7.5. The agents award 6–7 readily and
   will not reach 8–9. That is where prompt work should aim.
3. **Band anchors made it worse** (MAE 0.500 → 0.750 on matched items) and are
   off by default. Revisit with per-criterion anchors rather than whole
   truncated transcripts, if at all.
4. **Do not apply a post-hoc offset.** Adding +0.7 would take MAE near zero on
   this set, fit a constant to n=3, and fail on the first item outside this
   distribution.

## 5. Defects this exercise found

| defect | effect | fix |
|---|---|---|
| `MaxTokens: 1024` starved by extended thinking | 28/28 agent calls failed | raised to 8192 |
| truncation reported as 'unexpected end of JSON input' | cause hidden twice | explicit `max_tokens` guard, mirroring services/writing |
| Pronunciation returned band 0.0 while stating it had no evidence | cost a band-8 candidate 2.5 bands | abstains with `insufficient_evidence` |
| word confidence sent as `confidence`, read as `probability` | every word arrived 0.0; Pronunciation judged on pauses alone | field name corrected |

The last three share one shape: **a zero or a silence standing in for a missing
measurement.** It is the same defect as BUG-055 and BUG-035, and it recurs
because knowledge does not propagate between services — services/writing had
carried the max_tokens guard for some time before speaking rediscovered the need.
