package speaking

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"net/url"
	"runtime"
	"sync"
	"testing"
	"time"

	"github.com/gorilla/websocket"

	"github.com/ITI-OpenSource-Alex/GOA/services/speaking/db"
	"github.com/ITI-OpenSource-Alex/GOA/services/speaking/langfuse"
	"github.com/ITI-OpenSource-Alex/GOA/services/speaking/llm"
)

// mockDBRepo satisfies db.Repository for testing
type mockDBRepo struct{}

func (m *mockDBRepo) Create(ctx context.Context, session *db.SpeakingSession) error {
	return nil
}

func (m *mockDBRepo) ListByUser(ctx context.Context, userID string) ([]*db.SpeakingSessionSummary, error) {
	return nil, nil
}

func (m *mockDBRepo) GetByID(ctx context.Context, id string) (*db.SpeakingSession, error) {
	return nil, db.ErrSessionNotFound
}

func (m *mockDBRepo) CreateShareToken(ctx context.Context, sessionID string) (string, error) {
	return "", db.ErrSessionNotFound
}

func (m *mockDBRepo) GetByShareToken(ctx context.Context, token string) (*db.SpeakingSession, error) {
	return nil, db.ErrSessionNotFound
}

// mockLLMClient satisfies agents.LLMClient for testing
type mockLLMClient struct{}

func (m *mockLLMClient) StreamCompletion(ctx context.Context, systemPrompt, userPrompt string) (llm.CompletionResult, error) {
	return llm.CompletionResult{
		Text:             `{"band": 7.0, "feedback": "Good job.", "examples": ["example phrase"]}`,
		PromptTokens:     20,
		CompletionTokens: 15,
		LatencyMs:        150,
	}, nil
}

// mockTTSClient satisfies TTSClient for testing
type mockTTSClient struct{}

func (m *mockTTSClient) StreamTTS(ctx context.Context, text string, writeAudio func([]byte) error) error {
	// Write a mock 4-byte audio chunk
	return writeAudio([]byte{0, 1, 2, 3})
}

// mockLangfuseClient satisfies LangfuseClient for testing
type mockLangfuseClient struct{}

func (m *mockLangfuseClient) SendBatch(ctx context.Context, events []langfuse.IngestionEvent) error {
	return nil
}

func TestIntegrationE2EAudioStreaming(t *testing.T) {
	cfg := &Config{
		MaxConnections:   10,
		ElevenLabsAPIKey: "", // Triggers TTS API flow
	}

	dbRepo := &mockDBRepo{}
	llmClient := &mockLLMClient{}
	ttsClient := &mockTTSClient{}
	lfClient := &mockLangfuseClient{}

	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		HandleWebSocket(w, r, cfg, dbRepo, llmClient, ttsClient, lfClient)
	}))
	defer ts.Close()

	u, err := url.Parse(ts.URL)
	if err != nil {
		t.Fatal(err)
	}
	u.Scheme = "ws"
	u.Path = "/ws"

	ws, _, err := websocket.DefaultDialer.Dial(u.String(), nil)
	if err != nil {
		t.Fatalf("Failed to connect: %v", err)
	}
	defer ws.Close()

	// 1. Write the mandatory session_init control frame first
	initMsg := map[string]string{
		"type":           "session_init",
		"userId":         "user-123",
		"questionPrompt": "Describe a book you read.",
		"questionType":   "IELTS Part 2",
	}
	initBytes, _ := json.Marshal(initMsg)
	err = ws.WriteMessage(websocket.TextMessage, initBytes)
	if err != nil {
		t.Fatalf("Failed to send session_init control frame: %v", err)
	}

	// 2. Write binary chunks
	for i := 0; i < 3; i++ {
		err = ws.WriteMessage(websocket.BinaryMessage, []byte{0, 1, 2, 3})
		if err != nil {
			t.Fatalf("Failed to write binary message: %v", err)
		}
		time.Sleep(50 * time.Millisecond)
	}

	// 3. Wait for silence VAD ticker (1.5s silence gap + padding)
	time.Sleep(1800 * time.Millisecond)

	// 4. Read response transcript frame
	_, reply, err := ws.ReadMessage()
	if err != nil {
		t.Fatalf("Failed to read transcript response: %v", err)
	}

	var res map[string]interface{}
	err = json.Unmarshal(reply, &res)
	if err != nil {
		t.Fatalf("Failed to unmarshal response: %v", err)
	}

	if res["type"] != "transcript" {
		t.Errorf("Expected type 'transcript', got '%v'", res["type"])
	}
	if res["text"] == "" {
		t.Error("Expected non-empty transcript text")
	}

	// 5. Read evaluation response frame
	_, reply, err = ws.ReadMessage()
	if err != nil {
		t.Fatalf("Failed to read evaluation response: %v", err)
	}

	err = json.Unmarshal(reply, &res)
	if err != nil {
		t.Fatalf("Failed to unmarshal evaluation response: %v", err)
	}

	if res["type"] != "evaluation" {
		t.Errorf("Expected type 'evaluation', got '%v'", res["type"])
	}
	if res["overall_band"] != 7.0 {
		t.Errorf("Expected overall band 7.0, got %v", res["overall_band"])
	}

	// 6. Read synthesized TTS binary chunk
	msgType, audioBytes, err := ws.ReadMessage()
	if err != nil {
		t.Fatalf("Failed to read audio output chunk: %v", err)
	}
	if msgType != websocket.BinaryMessage {
		t.Errorf("Expected binary audio frame, got type %d", msgType)
	}
	if len(audioBytes) != 4 || audioBytes[0] != 0 {
		t.Errorf("Unexpected audio bytes: %v", audioBytes)
	}
}

func TestIntegrationMetricsAndSessionAccounting(t *testing.T) {
	cfg := &Config{
		MaxConnections:   10,
		ElevenLabsAPIKey: "",
	}

	dbRepo := &mockDBRepo{}
	llmClient := &mockLLMClient{}
	ttsClient := &mockTTSClient{}
	lfClient := &mockLangfuseClient{}

	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		HandleWebSocket(w, r, cfg, dbRepo, llmClient, ttsClient, lfClient)
	}))
	defer ts.Close()

	u, _ := url.Parse(ts.URL)
	u.Scheme = "ws"
	u.Path = "/ws"

	if activeConns != 0 {
		t.Fatalf("Expected baseline activeConns to be 0, got %d", activeConns)
	}

	ws, _, err := websocket.DefaultDialer.Dial(u.String(), nil)
	if err != nil {
		t.Fatalf("Failed to connect client: %v", err)
	}

	if activeConns != 1 {
		t.Errorf("Expected activeConns to be 1, got %d", activeConns)
	}

	ws.Close()

	// Wait for cleanup deferred routines to finish
	time.Sleep(150 * time.Millisecond)

	if activeConns != 0 {
		t.Errorf("Expected activeConns to return to 0 after disconnect, got %d", activeConns)
	}
}

func TestLoadConcurrentConnectionsAndLeaks(t *testing.T) {
	cfg := &Config{
		MaxConnections:   60,
		ElevenLabsAPIKey: "",
	}

	dbRepo := &mockDBRepo{}
	llmClient := &mockLLMClient{}
	ttsClient := &mockTTSClient{}
	lfClient := &mockLangfuseClient{}

	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		HandleWebSocket(w, r, cfg, dbRepo, llmClient, ttsClient, lfClient)
	}))
	defer ts.Close()

	u, _ := url.Parse(ts.URL)
	u.Scheme = "ws"
	u.Path = "/ws"

	concurrency := 50
	var wg sync.WaitGroup
	clients := make([]*websocket.Conn, concurrency)
	clientErrors := make([]error, concurrency)

	initialGoroutines := runtime.NumGoroutine()

	for i := 0; i < concurrency; i++ {
		wg.Add(1)
		go func(idx int) {
			defer wg.Done()
			ws, _, err := websocket.DefaultDialer.Dial(u.String(), nil)
			if err != nil {
				clientErrors[idx] = err
				return
			}
			clients[idx] = ws
		}(i)
	}

	wg.Wait()

	for idx, err := range clientErrors {
		if err != nil {
			t.Fatalf("Concurrent Client %d failed to connect: %v", idx, err)
		}
	}

	if activeConns != int32(concurrency) {
		t.Errorf("Expected activeConns to count %d, got %d", concurrency, activeConns)
	}

	for _, ws := range clients {
		if ws != nil {
			ws.Close()
		}
	}

	time.Sleep(1000 * time.Millisecond)

	if activeConns != 0 {
		t.Errorf("Expected activeConns to return to 0, got %d", activeConns)
	}

	finalGoroutines := runtime.NumGoroutine()
	margin := 10 // Allow small background system thread variations
	if finalGoroutines > initialGoroutines+margin {
		t.Errorf("Possible goroutine leak detected: started with %d, ended with %d", initialGoroutines, finalGoroutines)
	}
}
