package llm

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

// sseServer streams a synthetic Anthropic message built from the content blocks
// given, so the accumulation path can be driven through every shape the real
// provider actually produces.
func sseServer(t *testing.T, blocks []map[string]any, stopReason string) *httptest.Server {
	t.Helper()
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/event-stream")
		w.WriteHeader(http.StatusOK)
		flusher, _ := w.(http.Flusher)
		send := func(event string, data any) {
			raw, _ := json.Marshal(data)
			fmt.Fprintf(w, "event: %s\ndata: %s\n\n", event, raw)
			if flusher != nil {
				flusher.Flush()
			}
		}

		send("message_start", map[string]any{
			"type": "message_start",
			"message": map[string]any{
				"id": "msg_test", "type": "message", "role": "assistant",
				"model": "claude-opus-4-8", "content": []any{},
				"stop_reason": nil, "stop_sequence": nil,
				// Zero usage on purpose: telemetry.RecordLLMCost short-circuits
				// when both counts are zero, so these tests never touch Redis.
				// With real counts each subtest paid a 2s dial plus go-redis
				// retries against a host that does not resolve in CI -- pure
				// wall-clock and log noise for a side effect none of them assert.
				"usage": map[string]any{"input_tokens": 0, "output_tokens": 0},
			},
		})

		for i, block := range blocks {
			kind, _ := block["type"].(string)
			text, _ := block["text"].(string)

			start := map[string]any{"type": kind}
			deltaType := "text_delta"
			deltaKey := "text"
			switch kind {
			case "text":
				start["text"] = ""
			case "thinking":
				start["thinking"] = ""
				start["signature"] = ""
				deltaType = "thinking_delta"
				deltaKey = "thinking"
			}

			send("content_block_start", map[string]any{
				"type": "content_block_start", "index": i, "content_block": start,
			})
			if text != "" {
				send("content_block_delta", map[string]any{
					"type": "content_block_delta", "index": i,
					"delta": map[string]any{"type": deltaType, deltaKey: text},
				})
			}
			send("content_block_stop", map[string]any{"type": "content_block_stop", "index": i})
		}

		send("message_delta", map[string]any{
			"type":  "message_delta",
			"delta": map[string]any{"stop_reason": stopReason, "stop_sequence": nil},
			"usage": map[string]any{"output_tokens": 0},
		})
		send("message_stop", map[string]any{"type": "message_stop"})
	}))
	t.Cleanup(srv.Close)
	return srv
}

// TestStreamCompletion_RecoversTextAfterNonTextBlock is the regression guard for
// a bug measured against the real provider: the client read Content[0].Text, so
// a response that led with a thinking block yielded "" and the caller reported
// the criterion as unavailable. 24 of 32 real agent calls failed this way, which
// is how a working key and a working provider still produced only 1-3 of the 4
// IELTS criteria per session.
func TestStreamCompletion_RecoversTextAfterNonTextBlock(t *testing.T) {
	const answer = `{"band": 7.0, "feedback": "Clear and well organised.", "examples": []}`

	tests := []struct {
		name   string
		blocks []map[string]any
	}{
		{
			name:   "text only",
			blocks: []map[string]any{{"type": "text", "text": answer}},
		},
		{
			// The shape that broke: index 0 is not the answer.
			name: "thinking first, then text",
			blocks: []map[string]any{
				{"type": "thinking", "text": "Let me weigh the descriptors..."},
				{"type": "text", "text": answer},
			},
		},
		{
			// Long answers can arrive split; concatenation must reassemble them
			// or the JSON is truncated and parsing fails for a second reason.
			name: "text split across two blocks",
			blocks: []map[string]any{
				{"type": "text", "text": answer[:30]},
				{"type": "text", "text": answer[30:]},
			},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			srv := sseServer(t, tt.blocks, "end_turn")
			client := NewClient("claude-opus-4-8", "test-key", srv.URL)

			res, err := client.StreamCompletion(context.Background(), "system", "user")
			if err != nil {
				t.Fatalf("unexpected error: %v", err)
			}
			if res.Text != answer {
				t.Errorf("Text = %q, want %q", res.Text, answer)
			}
			// A response with no text block would leave this at zero; a real one
			// must record when the first text arrived.
			if res.FirstTokenMs < 0 {
				t.Errorf("FirstTokenMs = %d, want >= 0", res.FirstTokenMs)
			}
		})
	}
}

// TestStreamCompletion_EmptyBodyIsAnErrorNotACompletion. Returning "" let the
// caller fail with `unexpected end of JSON input (raw response: )`, which names
// the symptom and hides the cause. The error must say what actually came back.
func TestStreamCompletion_EmptyBodyIsAnErrorNotACompletion(t *testing.T) {
	tests := []struct {
		name   string
		blocks []map[string]any
		stop   string
	}{
		{"no content blocks at all", nil, "end_turn"},
		{"a single non-text block", []map[string]any{{"type": "thinking", "text": "hmm"}}, "end_turn"},
		{"an empty text block", []map[string]any{{"type": "text", "text": ""}}, "max_tokens"},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			srv := sseServer(t, tt.blocks, tt.stop)
			client := NewClient("claude-opus-4-8", "test-key", srv.URL)

			res, err := client.StreamCompletion(context.Background(), "system", "user")
			if err == nil {
				t.Fatalf("expected an error, got a completion with Text=%q", res.Text)
			}
			// The diagnosis has to be in the message, or this costs another
			// manual curl next time.
			if !strings.Contains(err.Error(), "no text") {
				t.Errorf("error should say the model returned no text, got: %v", err)
			}
			if !strings.Contains(err.Error(), "stop_reason") {
				t.Errorf("error should carry stop_reason, got: %v", err)
			}
			if !strings.Contains(err.Error(), "content_blocks") {
				t.Errorf("error should list the block types it did see, got: %v", err)
			}
		})
	}
}
