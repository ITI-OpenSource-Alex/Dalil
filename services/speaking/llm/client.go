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

// Model returns the effective model id this client calls with.
//
// SPEAK-EVAL-003: the Langfuse generation span used to carry a hardcoded
// "claude-3-5-haiku-20241022" while main() constructs two clients from
// configuration -- one for practice, one for exam -- and neither was Haiku. Every
// model-to-model comparison in the telemetry was therefore comparing one label
// against itself. Provenance has to be read from the thing that made the call.
func (c *Client) Model() string { return c.model }

func (c *Client) StreamCompletion(ctx context.Context, systemPrompt, userPrompt string) (CompletionResult, error) {
	return c.streamCompletion(ctx, systemPrompt, userPrompt, 8192)
}

// StreamShortCompletion is the low-latency path for the live interviewer. It
// deliberately cannot spend the scoring client's 8192-token budget on a
// one-sentence question.
func (c *Client) StreamShortCompletion(ctx context.Context, systemPrompt, userPrompt string) (CompletionResult, error) {
	return c.streamCompletion(ctx, systemPrompt, userPrompt, 64)
}

func (c *Client) streamCompletion(ctx context.Context, systemPrompt, userPrompt string, maxTokens int64) (CompletionResult, error) {
	start := time.Now()
	var firstTokenTime time.Time
	params := anthropic.MessageNewParams{
		Model: anthropic.Model(c.model),
		// 1024 was chosen when a response was a small JSON object and nothing
		// else. It predates the model emitting an extended-thinking block first.
		//
		// On a full-length transcript the thinking alone reaches the cap, the
		// response stops before any text is produced, and the agent receives
		// stop_reason="max_tokens" with content_blocks=[thinking] and no JSON to
		// parse. Every criterion then fails. SPEAK-EVAL-007's first benchmark run
		// hit this on all 28 agent calls -- four dead agents on every item -- and
		// the exam path, which concatenates all three parts into one transcript,
		// is the production path with the same shape.
		//
		// dev reached the same conclusion independently while stabilising the
		// holistic swarm, and set 8000. The exact figure does not matter -- both
		// clear the thinking block comfortably -- so this keeps 8192 for the round
		// number and records that two investigations converged on it. What dev's
		// fix did NOT include is the stop_reason guard below, which is what turns
		// the next occurrence into a named error instead of a parse failure.
		MaxTokens: maxTokens,
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

	// Text that stopped at the ceiling is truncated, and truncated JSON parses
	// as "unexpected end of JSON input" -- a message describing the symptom while
	// hiding the cause, which is how this cost a whole benchmark run twice.
	//
	// services/writing/app/agents.go has carried this exact check for some time,
	// with the same advice: raise the ceiling rather than retry, because a retry
	// reproduces the same truncation at the same cost. The lesson had not crossed
	// into this service. Saying so here is cheaper than rediscovering it a third
	// time.
	if msg.StopReason == "max_tokens" {
		return CompletionResult{}, fmt.Errorf(
			"model hit the max_tokens ceiling (%d output tokens); its response is "+
				"truncated and will not parse. Raise MaxTokens rather than retrying -- "+
				"a retry produces the same truncation",
			msg.Usage.OutputTokens,
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
