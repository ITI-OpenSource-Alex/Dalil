//go:build e2e

package handlers

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"testing"
	"time"

	fastws "github.com/fasthttp/websocket"
	"github.com/gofiber/websocket/v2"
)

// TestE2E_Measure re-measures the GOA-032 latency distribution against the REAL
// providers -- the faster-whisper/Piper sidecar and the real Anthropic endpoint
// -- through the real Gateway proxy.
//
// The ticket requires the SLO figures to be restated from a measured
// distribution rather than round numbers, and the earlier E2E runs used
// deterministic stand-ins whose timings describe the harness. This is the run
// whose numbers are allowed into slo.go.
//
//	E2E_MEASURE=1 E2E_MEASURE_SESSIONS=8 \
//	  go test -tags e2e -run TestE2E_Measure ./handlers/ -v -timeout 60m
//
// Each session costs 4 real completions. Keep the session count deliberate.
func TestE2E_Measure(t *testing.T) {
	if os.Getenv("E2E_MEASURE") == "" {
		t.Skip("set E2E_MEASURE=1 to run the real-provider measurement (it spends API credits)")
	}

	sessions := 8
	if raw := os.Getenv("E2E_MEASURE_SESSIONS"); raw != "" {
		fmt.Sscanf(raw, "%d", &sessions)
	}

	audio := loadFixtureAudio(t)
	audioMs := int64(len(audio)) / 32 // 16kHz * 2 bytes * mono
	t.Logf("fixture: %d bytes = %.1fs of real spoken English", len(audio), float64(audioMs)/1000)

	type run struct {
		transcriptMs     int64
		firstCriterionMs int64
		evaluationMs     int64
		firstAudioMs     int64
		completed        int
		transcript       string
		criteria         map[string]int64
	}
	var runs []run

	for i := 0; i < sessions; i++ {
		r, err := measureOne(t, fmt.Sprintf("measure-user-%d", i), audio)
		if err != nil {
			t.Errorf("session %d failed: %v", i+1, err)
			continue
		}
		runs = append(runs, run{
			transcriptMs:     r.transcriptMs,
			firstCriterionMs: r.firstCriterionMs,
			evaluationMs:     r.evaluationMs,
			firstAudioMs:     r.firstAudioMs,
			completed:        r.completed,
			transcript:       r.transcript,
			criteria:         r.criteria,
		})
		t.Logf("session %d/%d: transcript=%dms first_criterion=%dms evaluation=%dms first_audio=%dms completed=%d/4",
			i+1, sessions, r.transcriptMs, r.firstCriterionMs, r.evaluationMs, r.firstAudioMs, r.completed)
	}

	if len(runs) == 0 {
		t.Fatal("no sessions completed; nothing to measure")
	}

	collect := func(pick func(run) int64) []int64 {
		out := make([]int64, 0, len(runs))
		for _, r := range runs {
			if v := pick(r); v > 0 {
				out = append(out, v)
			}
		}
		sort.Slice(out, func(i, j int) bool { return out[i] < out[j] })
		return out
	}

	report := map[string]any{
		"measured_at":        time.Now().UTC().Format(time.RFC3339),
		"sessions_requested": sessions,
		"sessions_completed": len(runs),
		"audio_duration_ms":  audioMs,
		"providers":          "real faster-whisper + Piper sidecar; real Anthropic endpoint",
		"note": "Small sample. These are a starting point from one machine, " +
			"not a contract -- exactly as GOA-032 says of its own figures.",
	}

	for name, pick := range map[string]func(run) int64{
		"transcription_ms":           func(r run) int64 { return r.transcriptMs },
		"time_to_first_criterion_ms": func(r run) int64 { return r.firstCriterionMs },
		"e2e_evaluation_ms":          func(r run) int64 { return r.evaluationMs },
		"e2e_first_audio_ms":         func(r run) int64 { return r.firstAudioMs },
	} {
		values := collect(pick)
		if len(values) == 0 {
			continue
		}
		stats := map[string]any{
			"n":   len(values),
			"min": values[0],
			"med": values[len(values)/2],
			"max": values[len(values)-1],
			"p95": percentile(values, 0.95),
		}
		report[name] = stats
		t.Logf("%-28s n=%d min=%d med=%d p95=%d max=%d",
			name, len(values), values[0], stats["med"], stats["p95"], values[len(values)-1])
	}

	// The transcription budget is a RATIO, so report it as one.
	ratios := make([]int64, 0, len(runs))
	for _, r := range runs {
		if r.transcriptMs > 0 {
			ratios = append(ratios, r.transcriptMs*1000/audioMs) // milli-ratio
		}
	}
	sort.Slice(ratios, func(i, j int) bool { return ratios[i] < ratios[j] })
	if len(ratios) > 0 {
		report["transcription_ratio"] = map[string]any{
			"n":   len(ratios),
			"min": float64(ratios[0]) / 1000,
			"med": float64(ratios[len(ratios)/2]) / 1000,
			"p95": float64(percentile(ratios, 0.95)) / 1000,
			"max": float64(ratios[len(ratios)-1]) / 1000,
		}
		t.Logf("%-28s n=%d min=%.3f med=%.3f p95=%.3f max=%.3f",
			"transcription_ratio", len(ratios),
			float64(ratios[0])/1000, float64(ratios[len(ratios)/2])/1000,
			float64(percentile(ratios, 0.95))/1000, float64(ratios[len(ratios)-1])/1000)
	}

	if len(runs) > 0 {
		t.Logf("sample transcript: %q", truncate(runs[0].transcript, 160))
		report["sample_transcript"] = runs[0].transcript
	}

	out := filepath.Join("..", "..", "..", "perf", "reports",
		time.Now().UTC().Format("20060102T150405Z")+"-real-provider-measurement.json")
	blob, _ := json.MarshalIndent(report, "", "  ")
	if err := os.WriteFile(out, blob, 0o644); err != nil {
		t.Logf("could not write %s: %v", out, err)
	} else {
		t.Logf("wrote %s", out)
	}
}

type measurement struct {
	transcriptMs     int64
	firstCriterionMs int64
	evaluationMs     int64
	firstAudioMs     int64
	completed        int
	transcript       string
	criteria         map[string]int64
}

func measureOne(t *testing.T, userID string, audio []byte) (*measurement, error) {
	t.Helper()
	conn, _, err := e2eDial(t, e2eToken(t, userID))
	if err != nil {
		return nil, fmt.Errorf("upgrade: %w", err)
	}
	defer conn.Close()

	init, _ := json.Marshal(map[string]string{
		"type": "session_init", "userId": userID,
		"questionPrompt": "Describe a memorable journey you have taken. You should say where you went, " +
			"who you went with, what you did there, and explain why it was memorable.",
		"questionType": "IELTS Part 2",
	})
	if err := conn.WriteMessage(websocket.TextMessage, init); err != nil {
		return nil, fmt.Errorf("session_init: %w", err)
	}

	// Push the whole clip without artificial gaps, so the VAD silence window
	// fires once at the end rather than chopping the utterance into pieces.
	const chunk = 16000
	start := time.Now()
	for offset := 0; offset < len(audio); offset += chunk {
		end := offset + chunk
		if end > len(audio) {
			end = len(audio)
		}
		if err := conn.WriteMessage(websocket.BinaryMessage, audio[offset:end]); err != nil {
			return nil, fmt.Errorf("audio: %w", err)
		}
	}

	m := &measurement{criteria: map[string]int64{}}
	// Whisper on CPU over a 68s clip plus four real completions: generous, and
	// the point is to observe the tail rather than to clip it.
	_ = conn.SetReadDeadline(time.Now().Add(10 * time.Minute))

	for {
		msgType, raw, err := conn.ReadMessage()
		if err != nil {
			if _, ok := err.(*fastws.CloseError); ok && m.evaluationMs > 0 {
				break
			}
			return nil, fmt.Errorf("read: %w", err)
		}
		elapsed := time.Since(start).Milliseconds()
		if msgType == websocket.BinaryMessage {
			if m.firstAudioMs == 0 {
				m.firstAudioMs = elapsed
			}
			break // first audio chunk is all we time
		}
		var f map[string]any
		if err := json.Unmarshal(raw, &f); err != nil {
			return nil, fmt.Errorf("bad frame: %s", raw)
		}
		switch f["type"] {
		case "transcript":
			m.transcriptMs = elapsed
			m.transcript, _ = f["text"].(string)
		case "criterion":
			name, _ := f["criterion"].(string)
			m.criteria[name] = elapsed
			if m.firstCriterionMs == 0 {
				m.firstCriterionMs = elapsed
			}
			if f["timed_out"] != true {
				m.completed++
			}
		case "evaluation":
			m.evaluationMs = elapsed
		case "error":
			return nil, fmt.Errorf("session error: %v", f["message"])
		}
	}
	return m, nil
}

func loadFixtureAudio(t *testing.T) []byte {
	t.Helper()
	path := os.Getenv("E2E_AUDIO_FIXTURE")
	if path == "" {
		path = filepath.Join("..", "..", "..", "perf", "fixtures", "ielts-part2-answer.16k.pcm")
	}
	audio, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("real speech fixture not found at %s: %v\n"+
			"Generate it first -- synthetic noise makes Whisper's runtime meaningless.", path, err)
	}
	return audio
}

// percentile uses nearest-rank, which is honest about small samples: with n=8
// the 95th percentile IS the maximum, and interpolating would invent precision
// the sample does not have.
func percentile(sorted []int64, p float64) int64 {
	if len(sorted) == 0 {
		return 0
	}
	rank := int(float64(len(sorted))*p+0.5) - 1
	if rank < 0 {
		rank = 0
	}
	if rank >= len(sorted) {
		rank = len(sorted) - 1
	}
	return sorted[rank]
}

func truncate(s string, n int) string {
	if len(s) <= n {
		return s
	}
	return s[:n] + "..."
}
