package speaking

import (
	"bytes"
	"encoding/json"
	"fmt"
	"mime/multipart"
	"net/http"
	"net/textproto"
	"sync/atomic"
	"time"

	"github.com/ITI-OpenSource-Alex/GOA/services/speaking/agents"
	"github.com/gorilla/websocket"
	"github.com/rs/zerolog/log"
)

func (c *Client) transcribeAudio(audio []byte) {
	if c.speechURL == "" {
		log.Warn().Str("session_id", c.id).Msg("Speech Service URL is not configured, returning mock transcript")

		apiStart := time.Now()
		c.sendTranscript("Mock transcript (Speech URL missing)")
		apiDuration := time.Since(apiStart)

		transcriptionLatencyMetric.Observe(float64(apiDuration.Milliseconds()))
		atomic.StoreInt64(&c.lastTransMs, apiDuration.Milliseconds())

		// Trigger evaluation swarm directly using the mock transcript
		c.runEvaluationAndTTS("Mock transcript (Speech URL missing)", apiDuration.Milliseconds(), nil)
		return
	}
	// SPEAK-EVAL-002. The upload is labelled with what the client declared at
	// session_init, not with an assertion.
	//
	// This used to be a hardcoded filename="audio.pcm" and
	// Content-Type: audio/pcm;rate=16000 for every session. The sidecar decodes
	// anything matching audio/pcm with np.frombuffer(dtype=int16), so a browser's
	// WebM/Opus container was reinterpreted as raw samples and the transcript --
	// and every band derived from it -- described noise.
	//
	// An unknown format is refused here rather than guessed. Transcribing bytes
	// whose encoding nobody knows is the defect with an extra step.
	format, ok := lookupAudioFormat(c.audioFormat)
	if !ok {
		log.Error().
			Str("session_id", c.id).
			Str("declared_format", c.audioFormat).
			Msg("Cannot transcribe: session has no usable declared audio format")
		c.setOutcome("error")
		c.sendError("This recording's audio format was not recognised. Please refresh and try again.")
		return
	}

	log.Info().
		Str("session_id", c.id).
		Int("audio_size_bytes", len(audio)).
		Str("audio_format", format.mediaType).
		Msg("Calling local Speech-to-Text sidecar...")
	var resp *http.Response
	var err error
	for attempt := 0; attempt < 2; attempt++ {
		body := &bytes.Buffer{}
		writer := multipart.NewWriter(body)

		h := make(textproto.MIMEHeader)
		h.Set("Content-Disposition", fmt.Sprintf(
			`form-data; name="%s"; filename="%s"`, "audio", "audio"+format.extension,
		))
		h.Set("Content-Type", format.uploadContentType)
		part, errPart := writer.CreatePart(h)
		if errPart != nil {
			log.Error().Err(errPart).Str("session_id", c.id).Msg("Failed to create form file field")
			return
		}
		_, errPart = part.Write(audio)
		if errPart != nil {
			log.Error().Err(errPart).Str("session_id", c.id).Msg("Failed to write audio data to form part")
			return
		}
		err = writer.Close()
		if err != nil {
			log.Error().Err(err).Str("session_id", c.id).Msg("Failed to close multipart writer")
			return
		}

		url := fmt.Sprintf("%s/stt", c.speechURL)
		req, errReq := http.NewRequestWithContext(c.ctx, "POST", url, body)
		if errReq != nil {
			log.Error().Err(errReq).Str("session_id", c.id).Msg("Failed to create STT HTTP request")
			return
		}
		req.Header.Set("Content-Type", writer.FormDataContentType())

		// Time the local STT sidecar latency
		apiStart := time.Now()
		resp, err = httpClient.Do(req)
		apiDuration := time.Since(apiStart)
		if err == nil && resp.StatusCode == http.StatusOK {
			// Record metrics on success
			transcriptionLatencyMetric.Observe(float64(apiDuration.Milliseconds()))
			atomic.StoreInt64(&c.lastTransMs, apiDuration.Milliseconds())

			// Decode response
			defer resp.Body.Close()
			// The speech sidecar returns {"transcript": "..."} -- see
			// services/speech/app/main.py. Decoding `text` yielded an empty string
			// on every successful call, so the swarm graded an empty transcript
			// and the client received an empty transcript event (BUG-035).
			// GOA-133: the sidecar also returns the audio duration, per-segment
			// and per-word timings, and per-word recognition confidence. Two of
			// the four IELTS criteria are defined over exactly that, and none of
			// it was requested, parsed or forwarded -- so Fluency and
			// Pronunciation scored delivery from text that cannot express it.
			// Measured: 18.87s and 33.67s renderings of one script produced
			// byte-identical transcripts.
			var sttResp struct {
				Transcript string        `json:"transcript"`
				DurationS  float64       `json:"duration_s"`
				Words      []agents.Word `json:"words"`
			}
			err = json.NewDecoder(resp.Body).Decode(&sttResp)
			if err != nil {
				log.Error().Err(err).Str("session_id", c.id).Msg("Failed to decode STT response JSON")
				c.setOutcome("error")
				c.sendError("Could not read the transcription result.")
				return
			}

			// GOA-032's transcription SLO is a *ratio*, because CPU Whisper
			// scales with utterance length -- an absolute millisecond budget is
			// meaningless across a 30s Part 1 answer and a two-minute Part 2 one.
			//
			// SPEAK-EVAL-002: the denominator now comes from the sidecar's
			// measured duration_s (added by GOA-133) instead of being inferred
			// from the byte count. Inference assumed raw PCM at 16kHz/16-bit, and
			// Opus compresses roughly 9.5x -- measured on the test fixtures, 6
			// seconds of speech is 20,218 bytes as WebM and 192,000 as PCM. So on
			// the browser path this budget was dividing by a denominator an order
			// of magnitude too small and breaching continuously for a reason
			// nobody could act on.
			//
			// Skipped entirely (not recorded as zero) when the duration is
			// unknown: a recorded 0 is a claim that STT was instantaneous, which
			// drags P95 down and hides real breaches.
			audioMs := int64(sttResp.DurationS * 1000)
			if audioMs <= 0 && format.isRawPCM {
				// An older sidecar returns no duration. Only raw PCM can be
				// recovered from the byte count; for compressed audio the
				// measurement is simply unavailable.
				audioMs = pcmDurationMs(len(audio))
			}
			if audioMs > 0 {
				ratio := float64(apiDuration.Milliseconds()) / float64(audioMs)
				transcriptionRatioMetric.Observe(ratio)
				c.checkSLO(budgetTranscriptionRatio, ratio)
			} else {
				transcriptionDurationUnknownTotal.Inc()
				log.Warn().
					Str("session_id", c.id).
					Str("audio_format", format.mediaType).
					Msg("No audio duration available; transcription_ratio not recorded for this session")
			}

			// 1. Send text transcript to client
			c.sendTranscript(sttResp.Transcript)

			// Derive the features once per session and share them between the two
			// agents that need them. `ok` is false when the sidecar returned no
			// word timings -- an older deployment, say -- and the feature block is
			// then OMITTED rather than rendered as zeros.
			var features *agents.ProsodyFeatures
			if f, ok := agents.ComputeProsody(sttResp.Words, sttResp.DurationS); ok {
				features = &f
				recordProsodyMetrics(f)
			} else {
				prosodyUnavailableTotal.Inc()
				log.Warn().
					Str("session_id", c.id).
					Int("words", len(sttResp.Words)).
					Float64("duration_s", sttResp.DurationS).
					Msg("No prosody features; Fluency and Pronunciation scored without them")
			}

			// 2. Trigger evaluation swarm and TTS voice streaming pipeline
			c.runEvaluationAndTTS(sttResp.Transcript, apiDuration.Milliseconds(), features)
			return
		}
		if resp != nil {
			resp.Body.Close()
		}
		if attempt == 0 {
			log.Warn().Err(err).Str("session_id", c.id).Msg("Transient STT error, retrying in 500ms...")

			retryTimer := time.NewTimer(500 * time.Millisecond)
			select {
			case <-c.ctx.Done():
				retryTimer.Stop()
				return
			case <-retryTimer.C:
			}
		}
	}
	if err != nil {
		log.Error().Err(err).Str("session_id", c.id).Msg("STT HTTP request failed after retries")
		c.setOutcome("error")
		// Tell the client. Without this the socket stayed open and silent after a
		// failed transcription -- observed as a 180s hang with zero events, which
		// a UI can only render as a spinner that never resolves (BUG-036).
		c.sendError("Transcription is unavailable right now. Please try again.")
		return
	}
}

// sendError delivers a terminal error to the client over the same channel as
// every other frame. It deliberately does not touch c.conn directly: writePump
// owns the socket, and this runs on the transcription goroutine, so a direct
// write would race it. See Client.sendFrame.
func (c *Client) sendError(reason string) {
	payload, err := json.Marshal(map[string]interface{}{
		"type":    "error",
		"message": reason,
	})
	if err != nil {
		return
	}
	c.sendFrame(websocket.TextMessage, payload)
}

func (c *Client) sendTranscript(text string) {
	resBytes, err := json.Marshal(map[string]interface{}{
		"type":    "transcript",
		"text":    text,
		"isFinal": true,
	})
	if err != nil {
		log.Error().Err(err).Str("session_id", c.id).Msg("Failed to marshal transcription response")
		return
	}
	c.sendFrame(websocket.TextMessage, resBytes)
}
