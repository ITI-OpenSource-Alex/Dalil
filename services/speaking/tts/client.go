package tts

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"time"

	"github.com/rs/zerolog/log"
)

type Client struct {
	apiKey     string
	voiceID    string
	httpClient *http.Client
}

// NewClient initializes the ElevenLabs TTS client helper
func NewClient(apiKey string) *Client {
	return &Client{
		apiKey:  apiKey,
		voiceID: "21m00Tcm4TlvDq8ikWAM", // Default voice "Rachel"
		httpClient: &http.Client{
			Timeout: 30 * time.Second, // Streaming synthesis requires a higher timeout threshold
		},
	}
}

// StreamTTS requests text-to-speech conversion and pumps binary audio chunks to the writer callback
func (c *Client) StreamTTS(ctx context.Context, text string, writeAudio func([]byte) error) error {
	if c.apiKey == "" {
		log.Warn().Msg("ElevenLabs API Key missing, skipping TTS synthesis")
		return fmt.Errorf("ElevenLabs API key is not configured")
	}

	url := fmt.Sprintf("https://api.elevenlabs.io/v1/text-to-speech/%s/stream?output_format=mp3_22050_32", c.voiceID)

	reqBody, err := json.Marshal(map[string]interface{}{
		"text":     text,
		"model_id": "eleven_monolingual_v1",
	})
	if err != nil {
		return fmt.Errorf("failed to marshal JSON request body: %w", err)
	}

	req, err := http.NewRequestWithContext(ctx, "POST", url, bytes.NewBuffer(reqBody))
	if err != nil {
		return fmt.Errorf("failed to create http request object: %w", err)
	}

	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("xi-api-key", c.apiKey)

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return fmt.Errorf("TTS HTTP request connection failed: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		var errBuf bytes.Buffer
		_, _ = io.Copy(&errBuf, resp.Body)
		return fmt.Errorf("TTS API returned non-OK status %d: %s", resp.StatusCode, errBuf.String())
	}

	// Stream chunks as they arrive from ElevenLabs
	buf := make([]byte, 4096)
	for {
		n, err := resp.Body.Read(buf)
		if n > 0 {
			if writeErr := writeAudio(buf[:n]); writeErr != nil {
				return fmt.Errorf("audio destination write failed: %w", writeErr)
			}
		}
		if err == io.EOF {
			break
		}
		if err != nil {
			return fmt.Errorf("error reading streaming audio body: %w", err)
		}
	}

	return nil
}
