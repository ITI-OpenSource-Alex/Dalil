# Speaking test fixtures

## speaking_sample_35s.wav

35 seconds, mono, 16 kHz, 16-bit PCM — the format the speaking pipeline expects.

**Provenance:** excerpted (60s–95s) from *D-Day speech (Reagan)* on Wikimedia Commons:
<https://commons.wikimedia.org/wiki/File:D-Day_speech_(Reagan).ogg>

**Licence:** public domain. A work prepared by an officer or employee of the US Federal
Government as part of their official duties (17 U.S.C. §105), additionally marked
CC Public Domain Mark 1.0. Safe to commit and redistribute.

**Why this clip:** it is real human speech that transcribes cleanly through the local
faster-whisper sidecar (verified: 90 words, no recognition errors), which is all the
GOA-098 pipeline cases need. It is *not* a substitute for a genuine IELTS candidate
recording — see the limits below.

## What this fixture does and does not validate

**Validates (GOA-098):** audio in → transcript → 4-agent swarm → evaluation event → TTS
out → `speaking_sessions` row. The acceptance criteria are about events being produced
with the right shape, and content does not affect that.

**Does not validate (GOA-107):** band-score plausibility. Two reasons:

1. It is *prepared oratory*, not spontaneous conversation. Fluency and Coherence scores
   will be flattering in a way a real candidate's would not be.
2. It is delivered in the third person about a historical event, so it does not sound
   like a candidate answering about their own experience.

Pair it with the closest seeded Part 2 prompt — "Describe a very difficult task that you
succeeded in doing" — which the content genuinely addresses (a difficult mission
accomplished). Judging whether the resulting bands are *correct* still needs a real
recording from a known-level speaker.
