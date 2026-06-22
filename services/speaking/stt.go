package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"mime/multipart"
	"net/http"
	"net/textproto"
	"sync/atomic"
	"time"

	"github.com/rs/zerolog/log"
)

func (c *Client) transcribeAudio(audio []byte) {
	if c.apiKey == "" {
		log.Warn().Str("session_id", c.id).Msg("ElevenLabs API Key is not configured, returning mock transcript")

		apiStart := time.Now()
		c.sendTranscript("Mock transcript (ElevenLabs API Key missing)")
		apiDuration := time.Since(apiStart)

		transcriptionLatencyMetric.Observe(float64(apiDuration.Milliseconds()))
		e2eDuration := time.Since(c.e2eStart)
		e2eLatencyMetric.Observe(float64(e2eDuration.Milliseconds()))

		atomic.StoreInt64(&c.lastTransMs, apiDuration.Milliseconds())
		c.outcome = "completed"
		return
	}
	log.Info().
		Str("session_id", c.id).
		Int("audio_size_bytes", len(audio)).
		Msg("Calling ElevenLabs Speech-to-Text API...")
	var resp *http.Response
	var err error
	for attempt := 0; attempt < 2; attempt++ {
		body := &bytes.Buffer{}
		writer := multipart.NewWriter(body)
		err = writer.WriteField("model_id", "scribe_v2")
		if err != nil {
			log.Error().Err(err).Str("session_id", c.id).Msg("Failed to write model_id form field")
			return
		}
		h := make(textproto.MIMEHeader)
		h.Set("Content-Disposition", fmt.Sprintf(`form-data; name="%s"; filename="%s"`, "file", "audio.pcm"))
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
		req, errReq := http.NewRequestWithContext(c.ctx, "POST", "https://api.elevenlabs.io/v1/speech-to-text", body)
		if errReq != nil {
			log.Error().Err(errReq).Str("session_id", c.id).Msg("Failed to create STT HTTP request")
			return
		}
		req.Header.Set("Content-Type", writer.FormDataContentType())
		req.Header.Set("xi-api-key", c.apiKey)
		// Time the ElevenLabs API latency specifically
		apiStart := time.Now()
		resp, err = httpClient.Do(req)
		apiDuration := time.Since(apiStart)
		if err == nil && resp.StatusCode == http.StatusOK {
			// Record metrics on success
			transcriptionLatencyMetric.Observe(float64(apiDuration.Milliseconds()))
			e2eDuration := time.Since(c.e2eStart)
			e2eLatencyMetric.Observe(float64(e2eDuration.Milliseconds()))

			atomic.StoreInt64(&c.lastTransMs, apiDuration.Milliseconds())
			c.outcome = "completed"
			break
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
		c.outcome = "error"
		return
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		var errorDetails bytes.Buffer
		errorDetails.ReadFrom(resp.Body)
		log.Error().
			Int("status_code", resp.StatusCode).
			Str("response", errorDetails.String()).
			Str("session_id", c.id).
			Msg("ElevenLabs STT API returned non-OK status after retries")
		c.outcome = "error"
		return
	}
	var sttResp struct {
		Text string `json:"text"`
	}
	err = json.NewDecoder(resp.Body).Decode(&sttResp)
	if err != nil {
		log.Error().Err(err).Str("session_id", c.id).Msg("Failed to decode STT response JSON")
		return
	}
	c.sendTranscript(sttResp.Text)
}
func (c *Client) sendTranscript(text string) {
	response := map[string]interface{}{
		"type":    "transcript",
		"text":    text,
		"isFinal": true,
	}
	resBytes, err := json.Marshal(response)
	if err != nil {
		log.Error().Err(err).Str("session_id", c.id).Msg("Failed to marshal transcription response")
		return
	}
	sendTimer := time.NewTimer(2 * time.Second)
	defer sendTimer.Stop()
	select {
	case <-c.ctx.Done():
		return
	case c.send <- resBytes:
	case <-sendTimer.C:
		log.Error().Str("session_id", c.id).Msg("Timed out trying to send transcript back to client")
	}
}
