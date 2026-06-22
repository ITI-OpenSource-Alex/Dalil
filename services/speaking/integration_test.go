package main

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"net/url"
	"runtime"
	"sync"
	"testing"
	"time"

	"github.com/gorilla/websocket"
)

func TestIntegrationE2EAudioStreaming(t *testing.T) {
	// 1. Start a local HTTP test server
	cfg := &Config{
		MaxConnections:   10,
		ElevenLabsAPIKey: "", // Triggers STT mock fallback
	}
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		handleWebSocket(w, r, cfg)
	}))
	defer ts.Close()

	// Convert HTTP URL to WebSocket WS URL
	u, err := url.Parse(ts.URL)
	if err != nil {
		t.Fatal(err)
	}
	u.Scheme = "ws"
	u.Path = "/ws"

	// 2. Connect WebSocket client
	ws, _, err := websocket.DefaultDialer.Dial(u.String(), nil)
	if err != nil {
		t.Fatalf("Failed to connect: %v", err)
	}
	defer ws.Close()

	// 3. Write multiple binary chunks
	for i := 0; i < 3; i++ {
		err = ws.WriteMessage(websocket.BinaryMessage, []byte{0, 1, 2, 3})
		if err != nil {
			t.Fatalf("Failed to write binary message: %v", err)
		}
		time.Sleep(50 * time.Millisecond)
	}

	// 4. Wait for VAD silence window (1.5s silence gap + padding)
	time.Sleep(1700 * time.Millisecond)

	// 5. Read response from client channel
	_, reply, err := ws.ReadMessage()
	if err != nil {
		t.Fatalf("Failed to read message: %v", err)
	}

	var res map[string]interface{}
	err = json.Unmarshal(reply, &res)
	if err != nil {
		t.Fatalf("Failed to unmarshal response: %v", err)
	}

	// Verify transcript payload properties
	if res["type"] != "transcript" {
		t.Errorf("Expected type 'transcript', got '%v'", res["type"])
	}
	if res["text"] == "" {
		t.Error("Expected non-empty transcript text")
	}
	if res["isFinal"] != true {
		t.Errorf("Expected isFinal to be true, got %v", res["isFinal"])
	}
}

func TestIntegrationMetricsAndSessionAccounting(t *testing.T) {
	cfg := &Config{
		MaxConnections:   10,
		ElevenLabsAPIKey: "",
	}
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		handleWebSocket(w, r, cfg)
	}))
	defer ts.Close()

	u, _ := url.Parse(ts.URL)
	u.Scheme = "ws"
	u.Path = "/ws"

	// Verify baseline
	if activeConns != 0 {
		t.Fatalf("Expected baseline activeConns to be 0, got %d", activeConns)
	}

	// Connect client
	ws, _, err := websocket.DefaultDialer.Dial(u.String(), nil)
	if err != nil {
		t.Fatalf("Failed to connect client: %v", err)
	}

	// Verify increment
	if activeConns != 1 {
		t.Errorf("Expected activeConns to be 1, got %d", activeConns)
	}

	// Disconnect client
	ws.Close()

	// Wait for cleanup deferred routines to finish
	time.Sleep(150 * time.Millisecond)

	// Verify decrement
	if activeConns != 0 {
		t.Errorf("Expected activeConns to return to 0 after disconnect, got %d", activeConns)
	}
}

func TestLoadConcurrentConnectionsAndLeaks(t *testing.T) {
	cfg := &Config{
		MaxConnections:   60,
		ElevenLabsAPIKey: "",
	}
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		handleWebSocket(w, r, cfg)
	}))
	defer ts.Close()

	u, _ := url.Parse(ts.URL)
	u.Scheme = "ws"
	u.Path = "/ws"

	concurrency := 50
	var wg sync.WaitGroup
	clients := make([]*websocket.Conn, concurrency)
	clientErrors := make([]error, concurrency)

	// Capture baseline goroutine count
	initialGoroutines := runtime.NumGoroutine()

	// Connect 50 clients concurrently in goroutines
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

	// Assert connection successes
	for idx, err := range clientErrors {
		if err != nil {
			t.Fatalf("Concurrent Client %d failed to connect: %v", idx, err)
		}
	}

	// Verify the counter registers 50
	if activeConns != int32(concurrency) {
		t.Errorf("Expected activeConns to count %d, got %d", concurrency, activeConns)
	}

	// Close all connections concurrently
	for _, ws := range clients {
		if ws != nil {
			ws.Close()
		}
	}

	// Wait for background worker cleanups to complete
	time.Sleep(1000 * time.Millisecond)

	// Verify counter drops back to 0
	if activeConns != 0 {
		t.Errorf("Expected activeConns to return to 0, got %d", activeConns)
	}

	// Check for goroutine leak
	finalGoroutines := runtime.NumGoroutine()
	margin := 5 // Allow small background system thread variations
	if finalGoroutines > initialGoroutines+margin {
		t.Errorf("Possible goroutine leak detected: started with %d, ended with %d", initialGoroutines, finalGoroutines)
	}
}
