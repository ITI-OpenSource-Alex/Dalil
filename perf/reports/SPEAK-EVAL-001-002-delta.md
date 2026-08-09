# SPEAK-EVAL-001 / 002 — the browser audio contract

**Tickets:** SPEAK-EVAL-001 (prove the defect) · SPEAK-EVAL-002 (Option B contract)
**Branch:** `feat/GOA-133-137-architecture-remediation`
**Decision:** Option B — declare the real MIME type and let the sidecar decode.
Option A (AudioWorklet → raw PCM) was considered and deferred; see "ADR" below.

---

## The defect

`services/frontend/lib/audio-recorder.ts` created `new MediaRecorder(this.stream)`
with no `mimeType`. Browsers therefore emit an **encoded container** — WebM/Opus
on Chrome, Ogg/Opus on Firefox, MP4/AAC on Safari. Those bytes reached
`services/speaking/internal/speaking/stt.go`, which labelled every upload:

```go
filename="audio.pcm"
Content-Type: audio/pcm;rate=16000
```

and `services/speech/app/main.py` decoded anything matching `audio/pcm` with
`np.frombuffer(data, dtype=np.int16)` — reinterpreting a compressed Opus
container as raw 16-bit samples.

### Measured, against the running sidecar

Reproducing exactly what the old path fed to Whisper, using the committed Chrome
fixture:

| | Old path | Reality |
|---|---|---|
| Duration Whisper saw | **0.632 s** | 6.0 s |
| Transcript | **`""`** (empty) | *"I would like to talk about a journey that I took last summer…"* |
| Words returned | **0** | 25 |

The 9.5× duration error is not a coincidence: 6 seconds of speech is **20,218
bytes** as WebM/Opus and **192,000 bytes** as raw PCM. Reading the former as the
latter compresses the apparent timeline by exactly that factor.

**The transcript was empty, so the four agents were grading nothing.** Every
browser-originated practice score was produced from silence.

> [!NOTE]
> `stt.go` already carried a comment about BUG-035 — *"Decoding `text` yielded an
> empty string on every successful call, so the swarm graded an empty transcript."*
> That was diagnosed as a JSON field-name mismatch and fixed as one. The field
> name was genuinely wrong, but fixing it could never have produced a non-empty
> transcript while the audio was being decoded as noise. BUG-035 appears to have
> been half-diagnosed.

### Why it survived

The Go integration tests and the k6 load test **construct real PCM**. They
validated a contract no browser produces, and stayed green throughout. This is
the seventh instance of this repository's signature failure — a passing suite
over a broken system — and the most severe.

---

## SPEAK-EVAL-001 — the failing tests

`services/speaking/internal/speaking/audio_contract_test.go`, run against the
pre-fix service:

```
--- FAIL: TestBrowserAudioIsNotDeclaredAsPCM/chrome_webm/opus
    upload declared Content-Type "audio/pcm;rate=16000" for audio/webm;codecs=opus audio.
--- FAIL: TestBrowserAudioIsNotDeclaredAsPCM/firefox_ogg/opus
    upload declared Content-Type "audio/pcm;rate=16000" for audio/ogg;codecs=opus audio.
--- FAIL: TestBrowserAudioIsNotDeclaredAsPCM/safari_mp4/aac
    upload declared Content-Type "audio/pcm;rate=16000" for audio/mp4 audio.
--- FAIL: TestUndeclaredFormatIsRejected
    an undeclared format was uploaded as "audio/pcm;rate=16000"
```

`TestDeclaredPCMStillUploadsAsPCM` passed pre-fix and post-fix — the control that
proves the raw-PCM path is not collateral damage.

Fixtures are real encoded audio generated with ffmpeg from synthetic Piper speech
(no personal voice data committed): `services/speaking/testdata/browser/`.

---

## SPEAK-EVAL-002 — what shipped

### Frontend

| File | Change |
|---|---|
| `lib/audio-recorder.ts` | `selectRecordingMimeType()` picks a format via `MediaRecorder.isTypeSupported`, passes it to the constructor, and exposes `getMimeType()`. Throws `UnsupportedRecordingError` rather than recording something undeclarable. |
| `lib/speaking-websocket.ts` | `session_init` carries `protocolVersion: 2` and `audioFormat`. New `audio_end` control frame. Audio recorded during the handshake is **queued and flushed on open**. |
| `components/chat/chat-shell.tsx` | Format resolved *before* the socket is constructed; recorder started after connect; mismatch between requested and actual format fails the session loudly. |

The queue is not incidental. **Only the first chunk carries the container
header**, so dropping it makes the entire utterance undecodable rather than
merely shorter. The original code created the recorder inside the socket's
`connected` handler — after `session_init` had already been sent — so no format
could have been declared even if anyone had tried.

### Speaking service

| File | Change |
|---|---|
| `internal/speaking/audio_format.go` *(new)* | One registry of supported formats: canonical media type, upload Content-Type, file extension, and whether duration is derivable from byte count. |
| `internal/speaking/client.go` | `session_init` validates the declared format and **refuses the session** if it is missing, malformed or unsupported. `audio_end` handled idempotently. Unknown control frames ignored rather than fatal, so the protocol can be extended without lockstep deploys. |
| `internal/speaking/stt.go` | Upload labelled from the declared format. Duration taken from the sidecar's `duration_s`. |
| `internal/speaking/metrics.go` | `audio_format_rejected_total{reason}`, `audio_end_total`, `transcription_duration_unknown_total`. |

An undeclared format is **refused, not defaulted**. A default is a guess, and a
wrong guess here produces a confident band from noise — the defect with an extra
step.

### The second defect, exposed by the first

`slo.go`'s `pcmDurationMs` infers duration from byte count assuming raw PCM. On
the browser path that denominator was ~9.5× too small, so GOA-032's
`transcription_ratio` SLO (budget 0.6, measured from 12 real clips) has been
breaching continuously for a reason nobody could act on.

Fixed by using the sidecar's measured `duration_s` — which **GOA-133 added**. One
ticket's change supplied the fix for a bug the next ticket exposed. Byte-count
inference survives only for genuine raw PCM, and a test asserts no compressed
format may ever claim `isRawPCM`.

### Speech sidecar

The correct decode path already existed — the `else` branch writes a temp file
and lets faster-whisper decode via ffmpeg, which the image already installs. The
bug was purely that Go forced the wrong branch. Hardened anyway:

- A payload declaring `audio/pcm` whose bytes begin with a known container
  signature is a **400**, not something to work around. Raw PCM is headerless and
  cannot verify itself, so this branch is where a lie has to be caught.
- Odd-length "16-bit PCM" rejected.
- Temp-file suffix follows the declared type; unknown types get `.bin`, not
  `.wav`. A temp file whose name contradicts its bytes is the kind of small lie
  that let the original defect survive review.
- Undecodable media returns a typed **400**, not a 500 — a 500 sends whoever is
  on call to the wrong service.

---

## Verification

| Suite | Result |
|---|---|
| `services/speech/tests/` (in-image) | **32 passed, 0 skipped** |
| `services/speaking/...` (all packages) | **all ok** |
| `services/speaking/internal/speaking` under `-race` | **ok** |
| `services/frontend` `tsc --noEmit` | **clean** |

New coverage: 4 upload-contract tests, 8 format-validation tests, 8 protocol
tests for `audio_end`, and 12 sidecar tests.

### Live proof, against the running sidecar

```
mislabelled as PCM -> 400  Payload declared as audio/pcm;rate=16000 but begins
                           with a Matroska/WebM container signature.
declared honestly  -> 200  duration 6.0s | words 25
transcript: "I would like to talk about a journey that I took last summer. It was
             a trip to a small coastal..."
```

All three browser containers decode for real, and
`test_encoded_and_pcm_of_the_same_speech_agree` checks the transcripts of the
same utterance through WebM and through PCM overlap ≥0.8 — evidence that decoding
is *correct*, not merely *successful*.

### Tests that had to change, and why

`integration_test.go` and `streaming_test.go` now declare
`audioFormat: "audio/pcm;rate=16000"`. They were sending no format, which the
server now refuses. That is the contract working: those suites stayed green
through the entire defect precisely because they send a format no browser
produces, and they must keep testing that path honestly.

---

## ADR — why Option B

**Chosen: B.** Declare the real MIME type end to end and let the sidecar decode.

- The correct decode path already existed in the sidecar and works for all three
  browser containers via ffmpeg. The frontend work is a *declaration*, not a
  rebuild.
- Delivered in one pass with full coverage, against a deadline.

**Not chosen: A** (capture PCM via AudioWorklet, resample, send a versioned
binary framing protocol).

- More deterministic — VAD, duration and replay all become exact — and it removes
  the container-header coupling entirely.
- But it is a real frontend build with worklet lifecycle testing, and it does not
  fix anything B leaves broken.

**Revisit A if** streaming transcription is wanted (B's per-chunk fragments are
individually undecodable), or if browser encoder variance turns out to affect
scores.

---

## Known limits

- **Not verified in real browsers.** All three container formats are tested with
  ffmpeg-generated fixtures matching what each browser emits, and the format
  selection is unit-tested, but no Playwright run has driven a real Chromium,
  Firefox or WebKit microphone. That is SPEAK-EVAL-002's remaining acceptance
  criterion and the highest-value next step.
- **Safari is the residual risk.** `audio/mp4` is its only option and its
  `MediaRecorder` support has historically lagged; `selectRecordingMimeType`
  throws a clear error rather than failing silently, but the path is untested on
  real WebKit.
- **Historical sessions are unrecoverable.** Every browser-originated speaking
  score in the database was computed from an empty transcript. They should be
  treated as void rather than re-scored, since the audio was never stored.
