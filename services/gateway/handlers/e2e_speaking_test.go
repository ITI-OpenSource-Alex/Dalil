//go:build e2e

package handlers

import (
	"encoding/json"
	"fmt"
	"net/http"
	"os"
	"testing"
	"time"

	gatewayauth "github.com/ITI-OpenSource-Alex/GOA/services/gateway/auth"
	fastws "github.com/fasthttp/websocket"
	"github.com/gofiber/websocket/v2"
)

// GOA-032 / GOA-132 end-to-end. Build-tagged so it never runs in unit CI: it
// requires a live stack.
//
//	docker compose up -d postgres redis-gateway localstack speaking gateway
//	go test -tags e2e -run TestE2E ./handlers/ -v
//
// Everything this exercises is real -- the Gateway with its JWT middleware and
// Redis rate limiter, the Speaking service, Postgres, and three real HTTP/WS
// hops. Only the two external providers (the speech sidecar and AgentRouter)
// are stood in for, because their latency is the thing the tickets work around
// and an uncontrolled provider cannot prove anything about frame ordering.

func e2eGatewayURL() string {
	if v := os.Getenv("E2E_GATEWAY_URL"); v != "" {
		return v
	}
	return "http://localhost:8080"
}

func e2eToken(t *testing.T, userID string) string {
	t.Helper()
	secret := os.Getenv("E2E_JWT_SECRET")
	if secret == "" {
		secret = "supersecret_dev_key" // docker-compose.yml
	}
	token, err := gatewayauth.NewTokenService(secret, time.Hour, 24*time.Hour).
		NewAccessToken(gatewayauth.User{ID: userID, Email: userID + "@example.com"})
	if err != nil {
		t.Fatalf("mint token: %v", err)
	}
	return token
}

func e2eDial(t *testing.T, token string) (*fastws.Conn, *http.Response, error) {
	t.Helper()
	headers := http.Header{}
	if token != "" {
		// A browser cannot set headers on a handshake, so it sends the
		// access_token cookie instead. Exercising the cookie path is the point:
		// it is what makes the route work from a real browser.
		headers.Set("Cookie", "access_token="+token)
	}
	url := "ws" + e2eGatewayURL()[len("http"):] + "/api/speaking/ws"
	conn, resp, err := (&fastws.Dialer{HandshakeTimeout: 10 * time.Second}).Dial(url, headers)
	if conn != nil {
		t.Cleanup(func() { conn.Close() })
	}
	return conn, resp, err
}

// TestE2E_SpeakingSessionThroughGateway drives the whole user-facing flow:
// upgrade through the Gateway with a cookie, push audio, and watch criteria
// stream back one at a time ahead of the aggregate.
func TestE2E_SpeakingSessionThroughGateway(t *testing.T) {
	const userID = "e2e-user-1"
	conn, _, err := e2eDial(t, e2eToken(t, userID))
	if err != nil {
		t.Fatalf("upgrade through the gateway failed: %v", err)
	}

	init, _ := json.Marshal(map[string]string{
		"type":           "session_init",
		"userId":         userID,
		"questionPrompt": "Describe a memorable journey you have taken.",
		"questionType":   "IELTS Part 2",
	})
	if err := conn.WriteMessage(websocket.TextMessage, init); err != nil {
		t.Fatalf("session_init: %v", err)
	}

	// ~2 seconds of 16kHz 16-bit mono PCM, so the transcription-ratio SLO has a
	// real duration to divide by.
	audio := make([]byte, 2*16000*2)
	for i := range audio {
		audio[i] = byte(i % 251)
	}
	for offset := 0; offset < len(audio); offset += 16000 {
		end := offset + 16000
		if end > len(audio) {
			end = len(audio)
		}
		if err := conn.WriteMessage(websocket.BinaryMessage, audio[offset:end]); err != nil {
			t.Fatalf("audio: %v", err)
		}
		time.Sleep(100 * time.Millisecond)
	}

	start := time.Now()
	_ = conn.SetReadDeadline(time.Now().Add(90 * time.Second))

	type frame struct {
		kind    string
		name    string
		at      time.Duration
		payload map[string]any
	}
	var frames []frame
	var sawAudio bool
	var audioAt time.Duration

	for {
		msgType, raw, err := conn.ReadMessage()
		if err != nil {
			t.Fatalf("read after %v (%d frames so far): %v", time.Since(start), len(frames), err)
		}
		if msgType == websocket.BinaryMessage {
			if !sawAudio {
				sawAudio = true
				audioAt = time.Since(start)
				t.Logf("[%6.2fs] BINARY  first TTS chunk (%d bytes)", audioAt.Seconds(), len(raw))
			}
			break
		}
		var f map[string]any
		if err := json.Unmarshal(raw, &f); err != nil {
			t.Fatalf("bad JSON frame: %s", raw)
		}
		kind, _ := f["type"].(string)
		name, _ := f["criterion"].(string)
		at := time.Since(start)
		frames = append(frames, frame{kind, name, at, f})
		t.Logf("[%6.2fs] %-11s %s", at.Seconds(), kind, name)

		if kind == "error" {
			t.Fatalf("session failed: %v", f["message"])
		}
	}

	// --- assertions -------------------------------------------------------

	var criteria []frame
	var evaluation *frame
	for i := range frames {
		switch frames[i].kind {
		case "criterion":
			criteria = append(criteria, frames[i])
		case "evaluation":
			evaluation = &frames[i]
		}
	}

	if len(criteria) != 4 {
		t.Fatalf("expected 4 criterion frames, got %d", len(criteria))
	}
	if evaluation == nil {
		t.Fatal("never received the aggregate evaluation frame")
	}

	// THE ticket requirement: a criterion reaches the client before the swarm
	// has finished.
	//
	// The invariant that must hold against ANY provider is ordering — every
	// criterion frame precedes the aggregate. The *magnitude* of the spread is a
	// property of the provider, not of this code: the stand-in router delays
	// Pronunciation by 6s on purpose, so the gap is large and obvious, while a
	// real provider running four comparable prompts concurrently returns them
	// within a second or two of each other. Asserting a fixed gap against a real
	// provider tests the provider's variance, not the streaming.
	first, last := criteria[0], criteria[len(criteria)-1]
	if first.at >= evaluation.at {
		t.Errorf("the first criterion did not precede the aggregate — frames were batched")
	}
	if last.at > evaluation.at {
		t.Errorf("a criterion arrived after the aggregate; ordering is broken")
	}
	gap := last.at - first.at
	t.Logf("first criterion %v ahead of the last (%v vs %v); aggregate at %v",
		gap, first.at, last.at, evaluation.at)

	// Only the staggered stand-in can prove the magnitude, so only it asserts on
	// it. Set by the deterministic-provider setup; absent for real-provider runs.
	if os.Getenv("E2E_STAGGERED_PROVIDER") != "" && gap < 3*time.Second {
		t.Errorf("criteria arrived only %v apart against a provider that staggers "+
			"them by ~5.5s; they were batched rather than streamed", gap)
	}
	for i := 1; i < len(criteria); i++ {
		if criteria[i].at < criteria[i-1].at {
			t.Errorf("criterion frames arrived out of order")
		}
	}

	// Opcode preservation across the proxy.
	if !sawAudio {
		t.Error("no binary TTS frame arrived; JSON and audio may have been collapsed to one opcode")
	} else if audioAt < evaluation.at {
		t.Error("audio arrived before the evaluation frame")
	}

	if got := evaluation.payload["completed_count"]; got != 4.0 {
		t.Errorf("completed_count = %v, want 4", got)
	}
	if got := evaluation.payload["overall_band"]; got == nil {
		t.Error("overall_band missing with 4 criteria completed")
	} else {
		t.Logf("overall_band = %v", got)
	}
	for _, c := range criteria {
		if c.payload["timed_out"] == true {
			t.Errorf("criterion %q timed out unexpectedly", c.name)
		}
		if c.payload["band"] == nil {
			t.Errorf("criterion %q completed with no band", c.name)
		}
	}
}

// TestE2E_UnauthenticatedUpgradeRejected -- the socket must never open.
func TestE2E_UnauthenticatedUpgradeRejected(t *testing.T) {
	conn, resp, err := e2eDial(t, "")
	if err == nil {
		conn.Close()
		t.Fatal("an unauthenticated upgrade succeeded")
	}
	if resp == nil {
		t.Fatalf("expected an HTTP rejection, got a transport error: %v", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusUnauthorized {
		t.Fatalf("status = %d, want 401", resp.StatusCode)
	}
	t.Logf("PASS: unauthenticated upgrade rejected with %d before any socket opened", resp.StatusCode)
}

// TestE2E_ExpiredTokenRejected covers the other half of the criterion.
func TestE2E_ExpiredTokenRejected(t *testing.T) {
	secret := os.Getenv("E2E_JWT_SECRET")
	if secret == "" {
		secret = "supersecret_dev_key"
	}
	expired, err := gatewayauth.NewTokenService(secret, -time.Hour, time.Hour).
		NewAccessToken(gatewayauth.User{ID: "e2e-user-1", Email: "e2e@example.com"})
	if err != nil {
		t.Fatalf("mint: %v", err)
	}
	conn, resp, dialErr := e2eDial(t, expired)
	if dialErr == nil {
		conn.Close()
		t.Fatal("an expired token opened a socket")
	}
	if resp == nil || resp.StatusCode != http.StatusUnauthorized {
		t.Fatalf("expected 401, got %v (%v)", resp, dialErr)
	}
	t.Logf("PASS: expired token rejected with 401")
}

// TestE2E_SessionPersistedAndReadableThroughGateway closes the loop: the
// session written during the streaming test above must come back through the
// Gateway's REST proxy, scoped to the token's user.
func TestE2E_SessionPersistedAndReadableThroughGateway(t *testing.T) {
	token := e2eToken(t, "e2e-user-1")

	req, _ := http.NewRequest(http.MethodGet, e2eGatewayURL()+"/api/speaking/sessions", nil)
	req.Header.Set("Cookie", "access_token="+token)
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatalf("list sessions: %v", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("status = %d, want 200", resp.StatusCode)
	}

	var sessions []map[string]any
	if err := json.NewDecoder(resp.Body).Decode(&sessions); err != nil {
		t.Fatalf("decode: %v", err)
	}
	if len(sessions) == 0 {
		t.Fatal("no persisted sessions for this user; the streaming test must run first")
	}
	t.Logf("PASS: %d session(s) returned through the gateway, band=%v",
		len(sessions), sessions[0]["overall_band"])

	// The IDOR guard: a caller-supplied userId must not change whose data
	// comes back.
	req2, _ := http.NewRequest(http.MethodGet,
		fmt.Sprintf("%s/api/speaking/sessions?userId=%s", e2eGatewayURL(), "someone-else"), nil)
	req2.Header.Set("Cookie", "access_token="+token)
	resp2, err := http.DefaultClient.Do(req2)
	if err != nil {
		t.Fatalf("list with forged userId: %v", err)
	}
	defer resp2.Body.Close()
	var forged []map[string]any
	_ = json.NewDecoder(resp2.Body).Decode(&forged)
	if len(forged) != len(sessions) {
		t.Errorf("a caller-supplied userId changed the result set (%d vs %d): the query "+
			"parameter is reaching the speaking service", len(forged), len(sessions))
	} else {
		t.Logf("PASS: caller-supplied userId ignored; scope came from the token")
	}
}

// TestE2E_UnauthenticatedSessionListRejected. The old direct :8082 route had no
// auth at all; through the Gateway there is no anonymous read.
func TestE2E_UnauthenticatedSessionListRejected(t *testing.T) {
	resp, err := http.Get(e2eGatewayURL() + "/api/speaking/sessions")
	if err != nil {
		t.Fatalf("request: %v", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusUnauthorized {
		t.Fatalf("status = %d, want 401", resp.StatusCode)
	}
	t.Logf("PASS: anonymous session list rejected with 401")
}
