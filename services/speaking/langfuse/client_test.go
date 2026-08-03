package langfuse

import (
	"context"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/prometheus/client_golang/prometheus/testutil"
)

func TestClient_SendBatch(t *testing.T) {
	pubKey := "pk-123"
	secKey := "sk-123"

	// 1. Create a local mock HTTP test server
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// Assert path and method
		if r.URL.Path != "/api/public/ingestion" {
			t.Errorf("expected URL path /api/public/ingestion, got %s", r.URL.Path)
		}
		if r.Method != "POST" {
			t.Errorf("expected method POST, got %s", r.Method)
		}

		// Assert basic authentication header
		expectedAuth := base64.StdEncoding.EncodeToString([]byte(fmt.Sprintf("%s:%s", pubKey, secKey)))
		actualAuth := r.Header.Get("Authorization")
		if actualAuth != fmt.Sprintf("Basic %s", expectedAuth) {
			t.Errorf("expected Authorization header %q, got %q", fmt.Sprintf("Basic %s", expectedAuth), actualAuth)
		}

		// Assert JSON payload structure
		bodyBytes, err := io.ReadAll(r.Body)
		if err != nil {
			t.Fatal("failed to read HTTP request body")
		}

		var payload struct {
			Batch []any `json:"batch"`
		}
		err = json.Unmarshal(bodyBytes, &payload)
		if err != nil {
			t.Errorf("failed to parse JSON request payload: %v", err)
		}

		if len(payload.Batch) != 1 {
			t.Errorf("expected batch event size 1, got %d", len(payload.Batch))
		}

		// Return 200 OK
		w.WriteHeader(http.StatusOK)
		w.Write([]byte(`{"success": true}`))
	}))
	defer server.Close()

	// 2. Initialize the client to target the mock server
	client := NewClient(pubKey, secKey, server.URL)

	events := []IngestionEvent{
		{
			ID:        "event-123",
			Type:      "trace",
			Timestamp: time.Now(),
			Body: TraceBody{
				ID:        "trace-123",
				Name:      "speaking_evaluation",
				UserID:    "user-1",
				SessionID: "session-1",
			},
		},
	}

	// 3. Trigger batch send
	err := client.SendBatch(context.Background(), events)
	if err != nil {
		t.Fatalf("expected no error, got %v", err)
	}
}

func TestClient_SendBatchCountsPartialFailures(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusMultiStatus)
		_, _ = w.Write([]byte(`{"errors":[{"id":"event-2","status":400}]}`))
	}))
	defer server.Close()

	before := testutil.ToFloat64(ingestionFailures)
	client := NewClient("pk-123", "sk-123", server.URL)
	err := client.SendBatch(context.Background(), []IngestionEvent{
		{ID: "event-1", Type: "trace", Timestamp: time.Now(), Body: TraceBody{ID: "trace-1", Name: "one"}},
		{ID: "event-2", Type: "trace", Timestamp: time.Now(), Body: TraceBody{ID: "trace-2", Name: "two"}},
	})

	if err == nil {
		t.Fatal("expected partial-ingestion error")
	}
	after := testutil.ToFloat64(ingestionFailures)
	if got := after - before; got != 1 {
		t.Fatalf("expected one failed event, got counter increase %v", got)
	}
}

func TestClient_SendBatchCountsRejectedBatch(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		http.Error(w, "unavailable", http.StatusServiceUnavailable)
	}))
	defer server.Close()

	before := testutil.ToFloat64(ingestionFailures)
	client := NewClient("pk-123", "sk-123", server.URL)
	err := client.SendBatch(context.Background(), []IngestionEvent{
		{ID: "event-1", Type: "trace", Timestamp: time.Now(), Body: TraceBody{ID: "trace-1", Name: "one"}},
		{ID: "event-2", Type: "trace", Timestamp: time.Now(), Body: TraceBody{ID: "trace-2", Name: "two"}},
	})

	if err == nil {
		t.Fatal("expected rejected-batch error")
	}
	after := testutil.ToFloat64(ingestionFailures)
	if got := after - before; got != 2 {
		t.Fatalf("expected two failed events, got counter increase %v", got)
	}
}

func TestClient_SendBatchCountsNetworkFailure(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(http.ResponseWriter, *http.Request) {}))
	serverURL := server.URL
	server.Close()

	before := testutil.ToFloat64(ingestionFailures)
	client := NewClient("pk-123", "sk-123", serverURL)
	err := client.SendBatch(context.Background(), []IngestionEvent{
		{ID: "event-1", Type: "trace", Timestamp: time.Now(), Body: TraceBody{ID: "trace-1", Name: "one"}},
		{ID: "event-2", Type: "trace", Timestamp: time.Now(), Body: TraceBody{ID: "trace-2", Name: "two"}},
	})

	if err == nil {
		t.Fatal("expected network error")
	}
	after := testutil.ToFloat64(ingestionFailures)
	if got := after - before; got != 2 {
		t.Fatalf("expected two failed events, got counter increase %v", got)
	}
}

func TestObservationBodiesIncludeParentContext(t *testing.T) {
	span := SpanBody{
		ID:                  "span-1",
		TraceID:             "0123456789abcdef0123456789abcdef",
		ParentObservationID: "0123456789abcdef",
		Name:                "speaking_evaluation",
	}
	generation := GenerationBody{
		ID:                  "generation-1",
		TraceID:             span.TraceID,
		ParentObservationID: span.ID,
		Name:                "speaking_swarm",
	}

	encoded, err := json.Marshal([]any{span, generation})
	if err != nil {
		t.Fatal(err)
	}
	var payload []map[string]any
	if err := json.Unmarshal(encoded, &payload); err != nil {
		t.Fatal(err)
	}
	if payload[0]["parentObservationId"] != span.ParentObservationID {
		t.Fatalf("span parent was not serialized: %s", encoded)
	}
	if payload[1]["parentObservationId"] != span.ID {
		t.Fatalf("generation parent was not serialized: %s", encoded)
	}
}
