package llm

import (
	"context"
	"fmt"
	"os"
	"strings"
	"time"

	"github.com/ITI-OpenSource-Alex/GOA/services/speaking/internal/httpx"
	"github.com/ITI-OpenSource-Alex/GOA/services/speaking/internal/telemetry"

	"github.com/anthropics/anthropic-sdk-go"
	"github.com/anthropics/anthropic-sdk-go/option"
)

type Client struct {
	client *anthropic.Client
	model  string
}

// CompletionResult aggregates the generated text and tokens/latency telemetry

type CompletionResult struct {
	Text             string
	PromptTokens     int
	CompletionTokens int
	LatencyMs        int64
	FirstTokenMs     int64
}

// NewClient initializes the Anthropic client wrapper
func NewClient(model, apiKey, baseURL string) *Client {
	userAgent := os.Getenv("ANTHROPIC_USER_AGENT")
	if userAgent == "" {
		userAgent = "Kilo-Code/7.4.11 ai-sdk/provider-utils/4.0.27 runtime/bun/1.3.14"
	}

	opts := []option.RequestOption{
		option.WithHeader("User-Agent", userAgent),
		// GOA-032: without this the SDK builds its own http.Client per
		// llm.NewClient call -- and main() calls it twice (practice + exam) -- so
		// neither shares a connection to AgentRouter even though it is the same
		// host, and the four concurrent swarm agents each paid a fresh TLS
		// handshake.
		//
		// 180s, above swarmEvaluationTimeout (60s) on purpose: if the client
		// timeout fired first the caller would see an opaque transport error
		// instead of the context.DeadlineExceeded that the swarm's timeout arm is
		// built to catch and degrade gracefully on.
		option.WithHTTPClient(httpx.NewClient(180 * time.Second)),
	}

	if baseURL != "" {
		opts = append(opts, option.WithBaseURL(baseURL))
		opts = append(opts, option.WithAuthToken(apiKey))
	} else {
		opts = append(opts, option.WithAPIKey(apiKey))
	}

	c := anthropic.NewClient(opts...)
	return &Client{
		client: &c,
		model:  model,
	}
}

func (c *Client) StreamCompletion(ctx context.Context, systemPrompt, userPrompt string) (CompletionResult, error) {
	start := time.Now()
	var firstTokenTime time.Time
	params := anthropic.MessageNewParams{
		Model:     anthropic.Model(c.model),
		MaxTokens: 8000,
		System: []anthropic.TextBlockParam{
			{
				Text: systemPrompt,
			},
		},
		Messages: []anthropic.MessageParam{
			anthropic.NewUserMessage(anthropic.NewTextBlock(userPrompt)),
		},
	}

	stream := c.client.Messages.NewStreaming(ctx, params)
	defer stream.Close()

	var msg anthropic.Message

	for stream.Next() {
		event := stream.Current()
		// Accumulate the current event chunk into our final message structure
		err := msg.Accumulate(event)
		if err != nil {
			return CompletionResult{}, fmt.Errorf("failed to accumulate stream chunk: %w", err)
		}
		// When text content is first populated, record first token timestamp
		// Any text block, not just index 0 -- same reason as the accumulation
		// below. Anchoring on Content[0] meant a response that leads with a
		// non-text block recorded no first-token time at all.
		if firstTokenTime.IsZero() {
			for _, block := range msg.Content {
				if block.Type == "text" && block.Text != "" {
					firstTokenTime = time.Now()
					break
				}
			}
		}
	}

	// Check if any iteration errors occurred
	if err := stream.Err(); err != nil {
		return CompletionResult{}, fmt.Errorf("anthropic stream failed: %w", err)
	}
	latency := time.Since(start).Milliseconds()
	var firstTokenMs int64
	if !firstTokenTime.IsZero() {
		firstTokenMs = firstTokenTime.Sub(start).Milliseconds()
	}
	// Concatenate EVERY text block, rather than reading Content[0].
	//
	// Content[0] is only the answer when the model happens to emit exactly one
	// text block first. A response that leads with any non-text block -- a
	// thinking block, a tool_use block -- puts an empty .Text at index 0, and
	// the caller then tries to parse "" as JSON and reports the criterion as
	// unavailable. Measured against the real provider, 24 of 32 agent calls
	// failed this way with `unexpected end of JSON input (raw response: )`,
	// which is how a working provider and a working key still produced 1-3 of 4
	// criteria per session.
	var textBlocks strings.Builder
	blockTypes := make([]string, 0, len(msg.Content))
	for _, block := range msg.Content {
		blockTypes = append(blockTypes, string(block.Type))
		if block.Type == "text" {
			textBlocks.WriteString(block.Text)
		}
	}
	fullText := textBlocks.String()

	// An empty body is a failure, not a completion. Returning it lets the caller
	// fail to parse "" and report a parse error, which describes the symptom and
	// hides the cause -- so say what actually came back instead.
	if fullText == "" {
		return CompletionResult{}, fmt.Errorf(
			"model returned no text (stop_reason=%q, content_blocks=%v, output_tokens=%d)",
			msg.StopReason, blockTypes, msg.Usage.OutputTokens,
		)
	}

	userID, ok := ctx.Value("userID").(string)
	if !ok || userID == "" {
		userID = "anonymous"
	}

	telemetry.RecordLLMCost(userID, c.model, int64(msg.Usage.InputTokens), int64(msg.Usage.OutputTokens))

	return CompletionResult{
		Text:             fullText,
		PromptTokens:     int(msg.Usage.InputTokens),
		CompletionTokens: int(msg.Usage.OutputTokens),
		LatencyMs:        latency,
		FirstTokenMs:     firstTokenMs,
	}, nil

}
