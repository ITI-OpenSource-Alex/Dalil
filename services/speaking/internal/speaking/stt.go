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
		c.runEvaluationAndTTS("Mock transcript (Speech URL missing)", apiDuration.Milliseconds())
		return
	}
	log.Info().
		Str("session_id", c.id).
		Int("audio_size_bytes", len(audio)).
		Msg("Calling local Speech-to-Text sidecar...")
	var resp *http.Response
	var err error
	for attempt := 0; attempt < 2; attempt++ {
		body := &bytes.Buffer{}
		writer := multipart.NewWriter(body)

		h := make(textproto.MIMEHeader)
		h.Set("Content-Disposition", fmt.Sprintf(`form-data; name="%s"; filename="%s"`, "audio", "audio.pcm"))
		h.Set("Content-Type", "audio/pcm;rate=16000")
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

			// GOA-032: the transcription SLO is a *ratio*, because CPU Whisper
			// scales with utterance length -- an absolute millisecond budget is
			// meaningless across a 30s Part 1 answer and a two-minute Part 2 one.
			//
			// Skipped entirely (not recorded as zero) when the duration is
			// unknown: a recorded 0 is a claim that STT was instantaneous, which
			// drags P95 down and hides real breaches.
			if audioMs := pcmDurationMs(len(audio)); audioMs > 0 {
				ratio := float64(apiDuration.Milliseconds()) / float64(audioMs)
				transcriptionRatioMetric.Observe(ratio)
				c.checkSLO(budgetTranscriptionRatio, ratio)
			}

			// Decode response
			defer resp.Body.Close()
			// The speech sidecar returns {"transcript": "..."} -- see
			// services/speech/app/main.py. Decoding `text` yielded an empty string
			// on every successful call, so the swarm graded an empty transcript
			// and the client received an empty transcript event (BUG-035).
			var sttResp struct {
				Transcript string `json:"transcript"`
			}
			err = json.NewDecoder(resp.Body).Decode(&sttResp)
			if err != nil {
				log.Error().Err(err).Str("session_id", c.id).Msg("Failed to decode STT response JSON")
				c.setOutcome("error")
				c.sendError("Could not read the transcription result.")
				return
			}

			// 1. Send text transcript to client
			c.sendTranscript(sttResp.Transcript)

			// 2. Trigger evaluation swarm and TTS voice streaming pipeline
			c.runEvaluationAndTTS(sttResp.Transcript, apiDuration.Milliseconds())
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
