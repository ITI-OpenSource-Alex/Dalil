package llm

import (
	"context"
	"fmt"
	"time"
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
	opts := []option.RequestOption{
		option.WithAuthToken(apiKey),
		option.WithHeader("User-Agent", "Kilo-Code/7.4.11 ai-sdk/provider-utils/4.0.27 runtime/bun/1.3.14"),
	}
	if baseURL != "" {
		opts = append(opts, option.WithBaseURL(baseURL))
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
		MaxTokens: 1024,
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
		if len(msg.Content) > 0 && msg.Content[0].Text != "" && firstTokenTime.IsZero() {
			firstTokenTime = time.Now()
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
	var fullText string
	if len(msg.Content) > 0 {
		fullText = msg.Content[0].Text
	}
	
	telemetry.RecordLLMCost("anonymous", c.model, int64(msg.Usage.InputTokens), int64(msg.Usage.OutputTokens))
	
	return CompletionResult{
		Text:             fullText,
		PromptTokens:     int(msg.Usage.InputTokens),
		CompletionTokens: int(msg.Usage.OutputTokens),
		LatencyMs:        latency,
		FirstTokenMs:     firstTokenMs,
	}, nil

}
