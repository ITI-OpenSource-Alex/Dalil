# Load-test audio fixture

`ielts-part2-answer.16k.pcm` — 68.4s of real spoken English, 16kHz 16-bit mono
PCM, matching the `audio/pcm;rate=16000` that
`services/speaking/internal/speaking/stt.go` declares.

## Why a real recording and not synthetic bytes

Whisper's runtime depends on what it is decoding. Synthetic noise returns an
empty transcript almost immediately, so a load test built on it reports a
pipeline that never did any work — the swarm grades nothing, the run finishes
fast, and every latency number is a fiction. The measured ratio on this fixture
is ~0.33 (one second of CPU per three seconds of speech), which matches the
figures in `slo.go`.

## Regenerating it

The clip is synthesised through the speech sidecar's own Piper voice — a genuine
IELTS Part 2 long-turn answer — then resampled from Piper's 22.05kHz output to
16kHz mono. Bring the sidecar up and run the generator:

```bash
docker compose up -d speech
# scratch generator: POST /tts, parse the WAV chunks, resample, write raw PCM
```

The generator walks the RIFF chunk list rather than assuming a 44-byte header:
Piper emits a valid but not-always-minimal header, and a fixed offset slices
into the audio and changes the apparent duration.

Committed rather than generated on demand so load-test numbers stay comparable
between runs — a different clip means a different Whisper workload and the
before/after Prometheus snapshots stop meaning anything.
