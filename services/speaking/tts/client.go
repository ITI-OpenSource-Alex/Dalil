package tts

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"time"

	"github.com/ITI-OpenSource-Alex/GOA/services/speaking/internal/httpx"
	"github.com/rs/zerolog/log"
)

type Client struct {
	url        string
	httpClient *http.Client
}

// NewClient initializes the TTS client helper
func NewClient(url string) *Client {
	return &Client{
		url: url,
		// Shared pooled transport (GOA-032). Piper is local, so the win here is
		// keep-alive rather than TLS reuse -- but it is the same two upstreams as
		// STT, and one pool is what makes MaxIdleConnsPerHost mean anything.
		httpClient: httpx.NewClient(30 * time.Second),
	}
}

// StreamTTS requests text-to-speech conversion and pumps binary audio chunks to the writer callback
func (c *Client) StreamTTS(ctx context.Context, text string, writeAudio func([]byte) error) error {
	if c.url == "" {
		log.Warn().Msg("Speech service URL missing, skipping TTS synthesis")
		return fmt.Errorf("speech service URL is not configured")
	}

	url := fmt.Sprintf("%s/tts", c.url)

	reqBody, err := json.Marshal(map[string]interface{}{
		"text": text,
	})
	if err != nil {
		return fmt.Errorf("failed to marshal JSON request body: %w", err)
	}

	req, err := http.NewRequestWithContext(ctx, "POST", url, bytes.NewBuffer(reqBody))
	if err != nil {
		return fmt.Errorf("failed to create http request object: %w", err)
	}

	req.Header.Set("Content-Type", "application/json")

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

	// Stream chunks as they arrive from the local sidecar
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
