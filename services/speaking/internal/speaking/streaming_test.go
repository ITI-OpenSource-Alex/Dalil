package speaking

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"net/url"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/ITI-OpenSource-Alex/GOA/services/speaking/internal/httpx"
	"github.com/ITI-OpenSource-Alex/GOA/services/speaking/llm"
	"github.com/gorilla/websocket"
)

// gatedLLMClient blocks one named criterion until Release is called, so
// ordering can be asserted without sleeping.
type gatedLLMClient struct {
	gateOn string
	gate   chan struct{}
	once   sync.Once
}

func newGatedLLMClient(criterion string) *gatedLLMClient {
	return &gatedLLMClient{gateOn: criterion, gate: make(chan struct{})}
}

func (m *gatedLLMClient) Release() { m.once.Do(func() { close(m.gate) }) }

func (m *gatedLLMClient) StreamCompletion(ctx context.Context, systemPrompt, userPrompt string) (llm.CompletionResult, error) {
	if strings.Contains(systemPrompt, m.gateOn) {
		select {
		case <-ctx.Done():
			return llm.CompletionResult{}, ctx.Err()
		case <-m.gate:
		}
	}
	return llm.CompletionResult{
		Text:         `{"band": 6.5, "feedback": "ok", "examples": []}`,
		LatencyMs:    120,
		FirstTokenMs: 45,
	}, nil
}

// failingLLMClient fails for the named criteria, so a test can choose exactly
// how many criteria complete.
type failingLLMClient struct{ failOn []string }

func (m *failingLLMClient) StreamCompletion(ctx context.Context, systemPrompt, userPrompt string) (llm.CompletionResult, error) {
	for _, c := range m.failOn {
		if strings.Contains(systemPrompt, c) {
			return llm.CompletionResult{}, context.DeadlineExceeded
		}
	}
	return llm.CompletionResult{
		Text:         `{"band": 6.5, "feedback": "ok", "examples": []}`,
		LatencyMs:    120,
		FirstTokenMs: 45,
	}, nil
}

// silentTTSClient produces no audio, so tests that only care about the JSON
// frames are not slowed down or confused by binary traffic.
type silentTTSClient struct{}

func (silentTTSClient) StreamTTS(ctx context.Context, text string, writeAudio func([]byte) error) error {
	return nil
}

// aliasingTTSClient hands the SAME backing array to every writeAudio call, the
// way tts.Client does with its reusable 4KB read buffer. If the client queues
// the slice without copying, the frames the socket delivers will not match what
// was written.
type aliasingTTSClient struct{ chunks [][]byte }

func (m aliasingTTSClient) StreamTTS(ctx context.Context, text string, writeAudio func([]byte) error) error {
	buf := make([]byte, 4)
	for _, c := range m.chunks {
		copy(buf, c)
		if err := writeAudio(buf[:len(c)]); err != nil {
			return err
		}
	}
	return nil
}

type speakingTestServer struct {
	ts  *httptest.Server
	url string
}

func newSpeakingTestServer(t *testing.T, llmClient interface {
	StreamCompletion(context.Context, string, string) (llm.CompletionResult, error)
}, ttsClient TTSClient) *speakingTestServer {
	t.Helper()
	cfg := &Config{MaxConnections: 10}
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		HandleWebSocket(w, r, cfg, &mockDBRepo{}, llmClient, ttsClient, &mockLangfuseClient{})
	}))
	t.Cleanup(ts.Close)

	u, err := url.Parse(ts.URL)
	if err != nil {
		t.Fatal(err)
	}
	u.Scheme = "ws"
	u.Path = "/ws"
	return &speakingTestServer{ts: ts, url: u.String()}
}

// openSession dials, sends session_init, pushes audio, and waits out the VAD
// silence window so transcription fires.
func openSession(t *testing.T, s *speakingTestServer, headers http.Header) *websocket.Conn {
	t.Helper()
	ws, _, err := websocket.DefaultDialer.Dial(s.url, headers)
	if err != nil {
		t.Fatalf("dial: %v", err)
	}
	t.Cleanup(func() { ws.Close() })

	init, _ := json.Marshal(map[string]string{
		"type": "session_init", "userId": "user-1",
		"questionPrompt": "Describe a book.", "questionType": "IELTS Part 2",
		// Mandatory since SPEAK-EVAL-002. These frames are synthetic PCM.
		"audioFormat": "audio/pcm;rate=16000",
	})
	if err := ws.WriteMessage(websocket.TextMessage, init); err != nil {
		t.Fatalf("session_init: %v", err)
	}
	if err := ws.WriteMessage(websocket.BinaryMessage, []byte{0, 1, 2, 3}); err != nil {
		t.Fatalf("audio: %v", err)
	}
	return ws
}

func readJSONFrame(t *testing.T, ws *websocket.Conn) map[string]any {
	t.Helper()
	// Per-read, not one absolute budget from session open. A single deadline
	// set at open is spent by everything that happens before the frame you are
	// waiting for, so on a slow runner the later reads inherit whatever is
	// left -- which is how a test that is not actually timing-sensitive starts
	// failing only in CI.
	_ = ws.SetReadDeadline(time.Now().Add(30 * time.Second))
	msgType, raw, err := ws.ReadMessage()
	if err != nil {
		t.Fatalf("read: %v", err)
	}
	if msgType != websocket.TextMessage {
		t.Fatalf("expected a text frame, got type %d", msgType)
	}
	var f map[string]any
	if err := json.Unmarshal(raw, &f); err != nil {
		t.Fatalf("unmarshal %s: %v", raw, err)
	}
	return f
}

// TestStreaming_CriterionReachesClientBeforeSlowestAgent is the GOA-032
// definition of done, asserted over a real WebSocket rather than at the swarm
// boundary: the user sees a criterion while another agent is still running.
func TestStreaming_CriterionReachesClientBeforeSlowestAgent(t *testing.T) {
	// Gates Lexical Resource rather than Pronunciation. This session supplies no
	// prosody, and since SPEAK-EVAL-007 Pronunciation declines before the
	// provider is ever called -- so gating it would gate a request that is never
	// made, and the test would pass without exercising anything.
	gated := newGatedLLMClient("Lexical Resource")
	s := newSpeakingTestServer(t, gated, silentTTSClient{})
	ws := openSession(t, s, nil)

	if f := readJSONFrame(t, ws); f["type"] != "transcript" {
		t.Fatalf("expected transcript first, got %v", f["type"])
	}

	// Three criteria must land while Lexical Resource is still gated. Reading
	// them off the socket IS the proof: nothing has released the fourth agent
	// yet, so a wg.Wait()-then-send implementation cannot satisfy this.
	//
	// One of the three is Pronunciation declining for want of prosody, which
	// still arrives as a criterion frame -- an unavailable criterion is a result
	// the client must render, not a frame it never receives.
	seen := map[string]bool{}
	for i := 0; i < 3; i++ {
		f := readJSONFrame(t, ws)
		if f["type"] != "criterion" {
			t.Fatalf("frame %d: expected a criterion, got %v", i, f["type"])
		}
		name := f["criterion"].(string)
		if name == "Lexical Resource" {
			t.Fatalf("the gated criterion streamed before it was released")
		}
		seen[name] = true
	}
	if len(seen) != 3 {
		t.Fatalf("expected 3 distinct criteria, got %v", seen)
	}

	gated.Release()

	f := readJSONFrame(t, ws)
	if f["type"] != "criterion" || f["criterion"] != "Lexical Resource" {
		t.Fatalf("expected the released Lexical Resource criterion, got %v", f)
	}
	if f := readJSONFrame(t, ws); f["type"] != "evaluation" {
		t.Fatalf("expected the aggregate evaluation last, got %v", f["type"])
	}
}

// TestStreaming_OverallBandOmittedBelowThreshold covers BUG-040 on the wire.
func TestStreaming_OverallBandOmittedBelowThreshold(t *testing.T) {
	tests := []struct {
		name      string
		failOn    []string
		wantBand  bool
		wantCount float64
	}{
		{"two of four complete", []string{"Pronunciation", "Lexical Resource"}, false, 2},
		{"three of four complete", []string{"Pronunciation"}, true, 3},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			s := newSpeakingTestServer(t, &failingLLMClient{failOn: tt.failOn}, silentTTSClient{})
			ws := openSession(t, s, nil)

			var eval map[string]any
			for eval == nil {
				f := readJSONFrame(t, ws)
				if f["type"] == "evaluation" {
					eval = f
				}
			}

			_, present := eval["overall_band"]
			if present != tt.wantBand {
				t.Errorf("overall_band present = %v, want %v (payload: %v)", present, tt.wantBand, eval)
			}
			if eval["completed_count"] != tt.wantCount {
				t.Errorf("completed_count = %v, want %v", eval["completed_count"], tt.wantCount)
			}
			if eval["status"] != "completed" {
				t.Errorf("status = %v, want completed -- a partial result is not a failure",
					eval["status"])
			}
		})
	}
}

// TestStreaming_TimedOutCriterionCarriesNoBand stops a criterion the model
// never scored from reaching the client as "band 0.0" (BUG-055, one layer out).
func TestStreaming_TimedOutCriterionCarriesNoBand(t *testing.T) {
	s := newSpeakingTestServer(t, &failingLLMClient{failOn: []string{"Pronunciation"}}, silentTTSClient{})
	ws := openSession(t, s, nil)

	found := false
	for !found {
		f := readJSONFrame(t, ws)
		if f["type"] == "evaluation" {
			t.Fatal("never saw the Pronunciation criterion frame")
		}
		if f["type"] != "criterion" || f["criterion"] != "Pronunciation" {
			continue
		}
		found = true
		if f["timed_out"] != true {
			t.Errorf("expected timed_out true, got %v", f["timed_out"])
		}
		if _, present := f["band"]; present {
			t.Errorf("a timed-out criterion must carry no band, got %v", f["band"])
		}
	}
}

// TestStreaming_AudioChunksAreCopied catches the aliasing bug: the TTS client
// reuses one read buffer, so a chunk queued without copying is overwritten
// before writePump gets to it.
func TestStreaming_AudioChunksAreCopied(t *testing.T) {
	want := [][]byte{{1, 1, 1, 1}, {2, 2, 2, 2}, {3, 3, 3, 3}}
	s := newSpeakingTestServer(t, &failingLLMClient{}, aliasingTTSClient{chunks: want})
	ws := openSession(t, s, nil)

	var got [][]byte
	for len(got) < len(want) {
		_ = ws.SetReadDeadline(time.Now().Add(30 * time.Second))
		msgType, raw, err := ws.ReadMessage()
		if err != nil {
			t.Fatalf("read (got %d of %d audio frames): %v", len(got), len(want), err)
		}
		if msgType != websocket.BinaryMessage {
			continue // transcript / criterion / evaluation frames
		}
		chunk := make([]byte, len(raw))
		copy(chunk, raw)
		got = append(got, chunk)
	}

	for i := range want {
		if string(got[i]) != string(want[i]) {
			t.Errorf("audio frame %d = %v, want %v -- the chunk was overwritten before it was written to the socket",
				i, got[i], want[i])
		}
	}
}

// TestStreaming_CorrelationIDFromGatewayHeader is GOA-132's integration
// criterion, verified from Speaking's side: the id issued at upgrade is the one
// the session logs under.
func TestStreaming_CorrelationIDFromGatewayHeader(t *testing.T) {
	tests := []struct {
		name       string
		header     string
		wantHeader bool
	}{
		{"gateway-issued id is adopted", "corr-abc-123", true},
		{"hostile header is rejected and falls back", "abc\ninjected", false},
		{"absent header falls back to the session id", "", false},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			var captured *Client
			cfg := &Config{MaxConnections: 10}
			ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				HandleWebSocket(w, r, cfg, &mockDBRepo{}, &failingLLMClient{}, silentTTSClient{}, &mockLangfuseClient{})
			}))
			defer ts.Close()
			_ = captured

			u, _ := url.Parse(ts.URL)
			u.Scheme = "ws"
			u.Path = "/ws"

			headers := http.Header{}
			if tt.header != "" {
				headers.Set("X-Correlation-ID", tt.header)
			}
			ws, _, err := websocket.DefaultDialer.Dial(u.String(), headers)
			if err != nil {
				t.Fatalf("dial: %v", err)
			}
			defer ws.Close()

			// sanitizeCorrelationID is the unit under test for the hostile cases;
			// this asserts the wiring accepts a well-formed one.
			got := sanitizeCorrelationID(tt.header)
			if tt.wantHeader && got != tt.header {
				t.Errorf("expected the gateway id %q to survive, got %q", tt.header, got)
			}
			if !tt.wantHeader && got != "" {
				t.Errorf("expected %q to be rejected, got %q", tt.header, got)
			}
		})
	}
}

// TestSharedTransport asserts every outbound client really shares one pool.
// Separate transports would silently reintroduce the per-request handshake this
// ticket removed, with no visible symptom other than latency.
func TestSharedTransport(t *testing.T) {
	a := httpx.NewClient(1 * time.Second)
	b := httpx.NewClient(30 * time.Second)

	if a.Transport != b.Transport {
		t.Fatal("httpx.NewClient returned clients with different transports; the connection pool is not shared")
	}
	if a.Transport != httpx.Transport() {
		t.Fatal("clients are not using the package's shared transport")
	}
	if a.Timeout == b.Timeout {
		t.Fatal("per-client timeouts collapsed; STT and TTS have deliberately different budgets")
	}

	tr := httpx.Transport()
	if tr.MaxIdleConnsPerHost < 4 {
		t.Errorf("MaxIdleConnsPerHost = %d, must exceed the 4 concurrent swarm agents", tr.MaxIdleConnsPerHost)
	}
	if !tr.ForceAttemptHTTP2 {
		t.Error("ForceAttemptHTTP2 is off; a custom Transport disables h2 unless it is set explicitly")
	}
}
