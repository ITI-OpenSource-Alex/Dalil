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
