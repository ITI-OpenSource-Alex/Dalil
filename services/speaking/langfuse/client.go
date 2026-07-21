package langfuse

import (
	"bytes"
	"context"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"time"

	"github.com/rs/zerolog/log"
)

type Client struct {
	publicKey  string
	secretKey  string
	host       string
	httpClient *http.Client
}

// IngestionEvent represents a single Langfuse ingestion item
type IngestionEvent struct {
	ID        string    `json:"id"`
	Type      string    `json:"type"` // "trace" or "span" / "generation"
	Timestamp time.Time `json:"timestamp"`
	Body      any       `json:"body"`
}

// TraceBody maps the properties for root Langfuse traces
type TraceBody struct {
	ID        string         `json:"id"`
	Name      string         `json:"name"`
	UserID    string         `json:"userId,omitempty"`
	SessionID string         `json:"sessionId,omitempty"`
	Metadata  map[string]any `json:"metadata,omitempty"`
}

// GenerationBody maps properties for individual LLM call spans
type GenerationBody struct {
	ID        string         `json:"id"`
	TraceID   string         `json:"traceId"`
	Name      string         `json:"name"`
	StartTime time.Time      `json:"startTime"`
	EndTime   time.Time      `json:"endTime"`
	Model     string         `json:"model,omitempty"`
	Input     any            `json:"input,omitempty"`
	Output    any            `json:"output,omitempty"`
	Usage     map[string]int `json:"usage,omitempty"`
	Metadata  map[string]any `json:"metadata,omitempty"`
}

// NewClient initializes the Langfuse HTTP reporter client
func NewClient(publicKey, secretKey, host string) *Client {
	if host == "" {
		host = "https://cloud.langfuse.com"
	}
	return &Client{
		publicKey:  publicKey,
		secretKey:  secretKey,
		host:       host,
		httpClient: &http.Client{Timeout: 10 * time.Second},
	}
}

// SendBatch transmits ingestion events in a single batch HTTP POST request
func (c *Client) SendBatch(ctx context.Context, events []IngestionEvent) error {
	if c.publicKey == "" || c.secretKey == "" {
		log.Warn().Msg("Langfuse credentials are not configured, skipping ingestion report")
		return nil
	}

	payload := map[string]any{
		"batch": events,
	}

	bodyBytes, err := json.Marshal(payload)
	if err != nil {
		return fmt.Errorf("failed to serialize Langfuse payload: %w", err)
	}

	url := fmt.Sprintf("%s/api/public/ingestion", c.host)
	req, err := http.NewRequestWithContext(ctx, "POST", url, bytes.NewBuffer(bodyBytes))
	if err != nil {
		return fmt.Errorf("failed to create Langfuse HTTP request: %w", err)
	}

	// Basic Auth credentials encoding
	auth := base64.StdEncoding.EncodeToString([]byte(fmt.Sprintf("%s:%s", c.publicKey, c.secretKey)))
	req.Header.Set("Authorization", fmt.Sprintf("Basic %s", auth))
	req.Header.Set("Content-Type", "application/json")

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return fmt.Errorf("Langfuse POST request connection failed: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK && resp.StatusCode != http.StatusCreated {
		var errBuf bytes.Buffer
		_, _ = io.Copy(&errBuf, resp.Body)
		return fmt.Errorf("Langfuse API returned status code %d: %s", resp.StatusCode, errBuf.String())
	}

	log.Info().Int("events_count", len(events)).Msg("Successfully batch-ingested events into Langfuse")
	return nil
}
