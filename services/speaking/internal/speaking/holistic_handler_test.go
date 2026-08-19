package speaking

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/ITI-OpenSource-Alex/GOA/services/speaking/langfuse"
	"github.com/ITI-OpenSource-Alex/GOA/services/speaking/llm"
)

// holisticLLMStub returns a well-formed holistic criterion JSON for every call
// so all four swarm agents complete (band 7.0), giving a fully populated result
// to trace.
type holisticLLMStub struct{}

func (holisticLLMStub) StreamCompletion(ctx context.Context, systemPrompt, userPrompt string) (llm.CompletionResult, error) {
	return llm.CompletionResult{
		Text: `{"band": 7.0, "overall_feedback": "Solid, coherent response.",` +
			`"part_notes": {"Part 1": "clear"}, "examples": [{"part": 1, "quote": "q", "issue": "i"}],` +
			`"improvement_tip": "keep practising"}`,
		PromptTokens:     20,
		CompletionTokens: 15,
		LatencyMs:        120,
	}, nil
}

// captured is the wire shape of a Langfuse ingestion batch, decoded far enough
// to inspect the trace + observation events the handler emits.
type capturedBatch struct {
	Batch []struct {
		Type string `json:"type"`
		Body struct {
			ID        string         `json:"id"`
			TraceID   string         `json:"traceId"`
			Name      string         `json:"name"`
			SessionID string         `json:"sessionId"`
			UserID    string         `json:"userId"`
			Metadata  map[string]any `json:"metadata"`
		} `json:"body"`
	} `json:"batch"`
}

func TestHandleHolisticEvaluation_EmitsExamTrace(t *testing.T) {
	// A real langfuse.Client pointed at this stub captures the exact ingestion
	// payload the handler produces — the same client the practice path uses, so
	// the test exercises real serialization, not a hand-rolled fake.
	batchCh := make(chan capturedBatch, 1)
	lf := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		body, _ := io.ReadAll(r.Body)
		var b capturedBatch
		if err := json.Unmarshal(body, &b); err != nil {
			t.Errorf("langfuse payload not decodable: %v", err)
		}
		batchCh <- b
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{}`))
	}))
	defer lf.Close()

	// Non-empty credentials so SendBatch actually posts (it no-ops when unset).
	lfClient := langfuse.NewClient("pk-test", "sk-test", lf.URL)

	examSessionID := "exam-sess-abc123"
	reqBody, _ := json.Marshal(map[string]string{
		"concatenated_transcript": "Part 1:\nHello.\nPart 2:\nA longer answer.\nPart 3:\nFinal thoughts.",
		"user_id":                 "user-xyz",
		"exam_session_id":         examSessionID,
	})
	req := httptest.NewRequest(http.MethodPost, "/internal/evaluate/holistic", strings.NewReader(string(reqBody)))
	rec := httptest.NewRecorder()

	HandleHolisticEvaluation(rec, req, &Config{}, holisticLLMStub{}, lfClient)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}

	// The trace is reported from a detached goroutine, so wait for it.
	var batch capturedBatch
	select {
	case batch = <-batchCh:
	case <-time.After(3 * time.Second):
		t.Fatal("timed out waiting for Langfuse trace")
	}

	// Exactly one root trace + four child agent spans.
	var trace *struct {
		Type string `json:"type"`
		Body struct {
			ID        string         `json:"id"`
			TraceID   string         `json:"traceId"`
			Name      string         `json:"name"`
			SessionID string         `json:"sessionId"`
			UserID    string         `json:"userId"`
			Metadata  map[string]any `json:"metadata"`
		} `json:"body"`
	}
	childSpans := 0
	for i := range batch.Batch {
		ev := &batch.Batch[i]
		switch ev.Type {
		case "trace":
			if trace != nil {
				t.Fatalf("expected a single root trace, got a second: %s", ev.Body.Name)
			}
			trace = ev
		case "generation", "span":
			childSpans++
			// Every child span carries the exam_session_id and hangs off the
			// root trace.
			if got := fmt.Sprint(ev.Body.Metadata["exam_session_id"]); got != examSessionID {
				t.Errorf("child span %q missing exam_session_id: got %q", ev.Body.Name, got)
			}
			if ev.Body.TraceID != trace.Body.ID {
				t.Errorf("child span %q not linked to root trace: traceId=%q root=%q", ev.Body.Name, ev.Body.TraceID, trace.Body.ID)
			}
		}
	}

	if trace == nil {
		t.Fatal("no root trace emitted")
	}
	// The DoD's exam_session_id attribute: on the trace's sessionId and metadata.
	if trace.Body.SessionID != examSessionID {
		t.Errorf("root trace sessionId = %q, want %q", trace.Body.SessionID, examSessionID)
	}
	if got := fmt.Sprint(trace.Body.Metadata["exam_session_id"]); got != examSessionID {
		t.Errorf("root trace metadata.exam_session_id = %q, want %q", got, examSessionID)
	}
	// The DoD's four child agent spans (Fluency, Lexical, Grammar, Pronunciation).
	if childSpans != 4 {
		t.Errorf("expected 4 child agent spans, got %d", childSpans)
	}
}
