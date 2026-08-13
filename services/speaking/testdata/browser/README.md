# Browser-format audio fixtures (SPEAK-EVAL-001)

Real encoded audio in the exact containers browsers produce, because
`services/frontend/lib/audio-recorder.ts` records with `new MediaRecorder(stream)`
and no `mimeType`.

| Fixture | Browser it models | Codec |
|---|---|---|
| `chrome_webm_opus.webm` | Chrome / Edge | Opus in WebM |
| `firefox_ogg_opus.ogg` | Firefox | Opus in Ogg |
| `safari_mp4_aac.mp4` | Safari / WebKit | AAC in MP4 |
| `reference_pcm_s16le_16k.raw` | none — the control | raw s16le 16 kHz mono |

The last one is what the existing integration and k6 load tests construct. That
is why those tests stayed green while the browser path was broken: they validate
a contract no browser produces.

Note the sizes. Six seconds of speech is **20,218 bytes** as WebM/Opus and
**192,000 bytes** as raw PCM — 9.5x. `pcmDurationMs` infers duration from byte
count assuming PCM, so on the browser path GOA-032's `transcription_ratio` SLO
divided by a denominator roughly 9.5x too small.

## Regenerating

Derived from `perf/fixtures/prosody/p01-fluent.wav` (synthetic Piper speech, so
no personal voice data is committed), trimmed to 6 seconds:

```bash
docker run --rm \
  -v "$PWD/services/speaking/testdata:/td" \
  -v "$PWD/perf/fixtures/prosody:/src:ro" \
  --entrypoint sh goa-speech -c '
ffmpeg -y -i /src/p01-fluent.wav -t 6 -c:a libopus -b:a 24k -ar 48000 -ac 1 -f webm /td/browser/chrome_webm_opus.webm
ffmpeg -y -i /src/p01-fluent.wav -t 6 -c:a libopus -b:a 24k -ar 48000 -ac 1 -f ogg  /td/browser/firefox_ogg_opus.ogg
ffmpeg -y -i /src/p01-fluent.wav -t 6 -c:a aac -b:a 64k -ar 44100 -ac 1 -f mp4 -movflags +faststart /td/browser/safari_mp4_aac.mp4
ffmpeg -y -i /src/p01-fluent.wav -t 6 -f s16le -acodec pcm_s16le -ar 16000 -ac 1 /td/browser/reference_pcm_s16le_16k.raw
'
```

These are small and synthetic, so unlike the prosody `.wav` files they are
committed. `.gitignore` excludes `*.wav`, which these are not.
