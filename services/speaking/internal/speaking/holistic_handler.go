// internal/speaking/holistic_handler.go
package speaking

import (
	"context"
	"encoding/json"
	"net/http"
	"time"

	"github.com/ITI-OpenSource-Alex/GOA/services/speaking/agents"
	"github.com/ITI-OpenSource-Alex/GOA/services/speaking/langfuse"
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
)

var (
	holisticEvaluationLatency = promauto.NewHistogram(prometheus.HistogramOpts{
		Name:    "goa_speaking_holistic_evaluation_ms",
		Help:    "Latency of holistic speaking evaluations",
		Buckets: prometheus.LinearBuckets(1000, 1000, 10), // 1s to 10s
	})
)

// HandleHolisticEvaluation processes the full exam transcript and returns a holistic band score with extended feedback.
func HandleHolisticEvaluation(w http.ResponseWriter, r *http.Request, cfg *Config, llmClient agents.LLMClient, langfuseClient *langfuse.Client) {
	start := time.Now()
	defer func() {
		holisticEvaluationLatency.Observe(float64(time.Since(start).Milliseconds()))
	}()

	var payload struct {
		ConcatenatedTranscript string `json:"concatenated_transcript"`
		UserID                 string `json:"user_id"`
	}

	if err := json.NewDecoder(r.Body).Decode(&payload); err != nil {
		http.Error(w, "Invalid JSON payload", http.StatusBadRequest)
		return
	}

	if payload.ConcatenatedTranscript == "" {
		http.Error(w, "concatenated_transcript is required", http.StatusBadRequest)
		return
	}

	if payload.UserID == "" {
		payload.UserID = "anonymous"
	}

	ctx, cancel := context.WithTimeout(r.Context(), 15*time.Second)
	ctx = context.WithValue(ctx, "userID", payload.UserID)
	defer cancel()

	res, err := agents.EvaluateHolisticSwarm(ctx, llmClient, payload.ConcatenatedTranscript)
	if err != nil && res.Status == "failed" {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	if err := json.NewEncoder(w).Encode(res); err != nil {
		http.Error(w, "Failed to encode response", http.StatusInternalServerError)
	}

}
