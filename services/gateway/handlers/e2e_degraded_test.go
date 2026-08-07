//go:build e2e

package handlers

import (
	"encoding/json"
	"net/http"
	"os"
	"strings"
	"testing"
	"time"

	fastws "github.com/fasthttp/websocket"
	"github.com/gofiber/websocket/v2"
)

// Degraded-path end-to-end runs. These are separated from the happy path
// because each needs the provider fakes restarted with failure injection:
//
//	STT_RATIO=0.9 ./e2efakes.exe            -> TestE2E_Degraded_SLOViolation
//	FAIL_CRITERIA="Pronunciation,Lexical Resource" ./e2efakes.exe
//	                                        -> TestE2E_Degraded_NoOverallBand
//
// They are skipped unless E2E_DEGRADED names which mode the fakes are in, so a
// full `go test -tags e2e` run never silently asserts against the wrong setup.

func runSpeakingSession(t *testing.T, userID string) []map[string]any {
	t.Helper()
	conn, _, err := e2eDial(t, e2eToken(t, userID))
	if err != nil {
		t.Fatalf("upgrade: %v", err)
	}

	init, _ := json.Marshal(map[string]string{
		"type": "session_init", "userId": userID,
		"questionPrompt": "Describe a memorable journey you have taken.",
		"questionType":   "IELTS Part 2",
	})
	if err := conn.WriteMessage(websocket.TextMessage, init); err != nil {
		t.Fatalf("session_init: %v", err)
	}

	audio := make([]byte, 2*16000*2) // ~2s of 16kHz 16-bit mono
	for i := range audio {
		audio[i] = byte(i % 251)
	}
	if err := conn.WriteMessage(websocket.BinaryMessage, audio); err != nil {
		t.Fatalf("audio: %v", err)
	}

	_ = conn.SetReadDeadline(time.Now().Add(90 * time.Second))
	var frames []map[string]any
	for {
		msgType, raw, err := conn.ReadMessage()
		if err != nil {
			if _, ok := err.(*fastws.CloseError); ok {
				break
			}
			t.Fatalf("read (%d frames): %v", len(frames), err)
		}
		if msgType == websocket.BinaryMessage {
			break
		}
		var f map[string]any
		if err := json.Unmarshal(raw, &f); err != nil {
			t.Fatalf("bad frame: %s", raw)
		}
		frames = append(frames, f)
		t.Logf("frame: %v %v", f["type"], f["criterion"])
		if f["type"] == "evaluation" || f["type"] == "error" {
			break
		}
	}
	return frames
}

func metricsText(t *testing.T) string {
	t.Helper()
	url := os.Getenv("E2E_SPEAKING_URL")
	if url == "" {
		url = "http://localhost:8082"
	}
	resp, err := http.Get(url + "/metrics")
	if err != nil {
		t.Fatalf("metrics: %v", err)
	}
	defer resp.Body.Close()
	buf := make([]byte, 512*1024)
	n, _ := resp.Body.Read(buf)
	full := string(buf[:n])
	for n > 0 {
		n, _ = resp.Body.Read(buf)
		full += string(buf[:n])
	}
	return full
}

// TestE2E_Degraded_SLOViolation proves the labelled counter fires for the right
// budget against a live service, not just in a unit test.
func TestE2E_Degraded_SLOViolation(t *testing.T) {
	if os.Getenv("E2E_DEGRADED") != "slo" {
		t.Skip("set E2E_DEGRADED=slo and run the fakes with STT_RATIO=0.9")
	}

	before := metricsText(t)
	runSpeakingSession(t, "e2e-slo-user")
	after := metricsText(t)

	const series = `goa_speaking_slo_violations_total{budget="transcription_ratio"}`
	if !strings.Contains(after, series) {
		t.Fatalf("expected the counter to appear with the transcription_ratio label; metrics:\n%s",
			filterLines(after, "slo_violations"))
	}
	t.Logf("before: %s", filterLines(before, "slo_violations"))
	t.Logf("after:  %s", filterLines(after, "slo_violations"))

	// The label must be the specific budget, not a catch-all: distinguishing a
	// slow sidecar from a slow provider is the reason it is labelled at all.
	if strings.Contains(after, `goa_speaking_slo_violations_total{budget="e2e_latency_ms"}`) {
		t.Log("note: the e2e budget also breached, which is expected when STT is 3x slower")
	}
}

// TestE2E_Degraded_NoOverallBand is BUG-040 end to end: with only 2 of 4
// criteria completing, the payload must carry the completed criteria and no
// overall figure at all.
func TestE2E_Degraded_NoOverallBand(t *testing.T) {
	if os.Getenv("E2E_DEGRADED") != "partial" {
		t.Skip(`set E2E_DEGRADED=partial and run the fakes with FAIL_CRITERIA="Pronunciation,Lexical Resource"`)
	}

	frames := runSpeakingSession(t, "e2e-partial-user")

	var criteria []map[string]any
	var evaluation map[string]any
	for _, f := range frames {
		switch f["type"] {
		case "criterion":
			criteria = append(criteria, f)
		case "evaluation":
			evaluation = f
		case "error":
			t.Fatalf("session errored: %v", f["message"])
		}
	}

	if len(criteria) != 4 {
		t.Errorf("expected 4 criterion frames even with 2 failures, got %d -- a criterion "+
			"that fails silently leaves the UI waiting on a frame that never comes", len(criteria))
	}
	timedOut := 0
	for _, c := range criteria {
		if c["timed_out"] == true {
			timedOut++
			if _, present := c["band"]; present {
				t.Errorf("failed criterion %v carries a band: %v", c["criterion"], c["band"])
			}
		}
	}
	if timedOut != 2 {
		t.Errorf("expected 2 failed criteria, got %d", timedOut)
	}

	if evaluation == nil {
		t.Fatal("no aggregate evaluation frame")
	}
	if evaluation["status"] != "completed" {
		t.Errorf("status = %v, want completed -- a partial result is not a failure", evaluation["status"])
	}
	if got := evaluation["completed_count"]; got != 2.0 {
		t.Errorf("completed_count = %v, want 2", got)
	}
	if band, present := evaluation["overall_band"]; present {
		t.Errorf("overall_band = %v, but only 2 criteria completed; a band averaged from "+
			"2 surviving agents describes which agents survived, not the candidate (BUG-040)", band)
	} else {
		t.Log("PASS: overall_band absent with 2 of 4 criteria completed")
	}

	// And the same must hold in persisted history: null, not 0.0.
	//
	// Polled, because the session is written from a detached goroutine after the
	// evaluation frame is sent -- deliberately, so persistence never delays the
	// user's result. Reading immediately is a race in the test, not in the
	// service.
	var sessions []map[string]any
	for attempt := 0; attempt < 20; attempt++ {
		req, _ := http.NewRequest(http.MethodGet, e2eGatewayURL()+"/api/speaking/sessions", nil)
		req.Header.Set("Cookie", "access_token="+e2eToken(t, "e2e-partial-user"))
		resp, err := http.DefaultClient.Do(req)
		if err != nil {
			t.Fatalf("list: %v", err)
		}
		sessions = nil
		_ = json.NewDecoder(resp.Body).Decode(&sessions)
		resp.Body.Close()
		if len(sessions) > 0 {
			break
		}
		time.Sleep(250 * time.Millisecond)
	}
	if len(sessions) == 0 {
		t.Fatal("session was not persisted within 5s")
	}
	if band := sessions[0]["overall_band"]; band != nil {
		t.Errorf("persisted overall_band = %v, want null -- history would render "+
			"'Band 0.0' for a session that produced no band", band)
	} else {
		t.Log("PASS: persisted overall_band is null, not 0.0")
	}
}

func filterLines(text, needle string) string {
	var out []string
	for _, line := range strings.Split(text, "\n") {
		if strings.Contains(line, needle) && !strings.HasPrefix(line, "#") {
			out = append(out, line)
		}
	}
	if len(out) == 0 {
		return "(no matching series)"
	}
	return strings.Join(out, " | ")
}
