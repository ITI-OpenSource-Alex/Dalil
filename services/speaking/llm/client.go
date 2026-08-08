package llm

import (
	"context"
	"fmt"
	"os"
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
	userAgent := os.Getenv("ANTHROPIC_USER_AGENT")
	if userAgent == "" {
		userAgent = "Kilo-Code/7.4.11 ai-sdk/provider-utils/4.0.27 runtime/bun/1.3.14"
	}

	opts := []option.RequestOption{
		option.WithHeader("User-Agent", userAgent),
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
		// When text content is first populated, record first token timestamp.
		// The gateway may prepend a thinking block (empty .Text), so scan every
		// block rather than assuming Content[0] is the answer text.
		if firstTokenTime.IsZero() {
			for _, block := range msg.Content {
				if block.Text != "" {
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
	// Concatenate every text block, skipping any thinking block the gateway
	// prepends (its .Text is empty), so we never return an empty answer while
	// a thinking block sits at Content[0].
	var fullText string
	for _, block := range msg.Content {
		if block.Text != "" {
			fullText += block.Text
		}
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
