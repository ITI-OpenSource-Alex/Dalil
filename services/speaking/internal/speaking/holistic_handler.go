// internal/speaking/holistic_handler.go
package speaking

import (
	"context"
	"encoding/json"
	"net/http"
	"strings"
	"time"

	"github.com/ITI-OpenSource-Alex/GOA/services/speaking/agents"
	"github.com/ITI-OpenSource-Alex/GOA/services/speaking/langfuse"
	"github.com/google/uuid"
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
	"github.com/rs/zerolog/log"
)

var (
	holisticEvaluationLatency = promauto.NewHistogram(prometheus.HistogramOpts{
		Name:    "goa_speaking_holistic_evaluation_ms",
		Help:    "Latency of holistic speaking evaluations",
		Buckets: prometheus.LinearBuckets(1000, 1000, 10), // 1s to 10s
	})
)

// holisticCriteria fixes the order the four swarm agents are traced in, so the
// child spans always read Fluency → Lexical → Grammar → Pronunciation
// regardless of the map iteration order of the swarm result.
var holisticCriteria = []string{
	"Fluency and Coherence",
	"Lexical Resource",
	"Grammatical Range and Accuracy",
	"Pronunciation",
}

// HandleHolisticEvaluation processes the full exam transcript and returns a holistic band score with extended feedback.
func HandleHolisticEvaluation(w http.ResponseWriter, r *http.Request, cfg *Config, llmClient agents.LLMClient, langfuseClient *langfuse.Client) {
	start := time.Now()
	defer func() {
		holisticEvaluationLatency.Observe(float64(time.Since(start).Milliseconds()))
	}()

	var payload struct {
		ConcatenatedTranscript string `json:"concatenated_transcript"`
		UserID                 string `json:"user_id"`
		ExamSessionID          string `json:"exam_session_id"`
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

	// The four criterion agents stream concurrently; each is capped at 110s
	// (see attemptTimeout in holistic.go), so the swarm's worst-case wall-clock
	// is ~110s and the common case is ~40s. 120s gives headroom over the cap
	// while staying under the exam client's 130s call timeout. A criterion that
	// genuinely hangs past 110s is dropped from the average rather than sinking
	// the whole request.
	ctx, cancel := context.WithTimeout(r.Context(), 120*time.Second)
	ctx = context.WithValue(ctx, "userID", payload.UserID)
	defer cancel()

	swarmStart := time.Now()
	res, err := agents.EvaluateHolisticSwarm(ctx, llmClient, payload.ConcatenatedTranscript)
	swarmEnd := time.Now()
	if err != nil && res.Status == "failed" {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	// Audit the exam evaluation to Langfuse: one root trace carrying the
	// exam_session_id, with a child agent span per rubric criterion. Reuses the
	// same ingestion client as the practice path (client.go) — this is the exam
	// counterpart of that WebSocket trace, not a second tracing system. Done in
	// a detached goroutine so reporting never blocks or fails the HTTP response.
	reportHolisticTrace(langfuseClient, payload.UserID, payload.ExamSessionID, payload.ConcatenatedTranscript, res, swarmStart, swarmEnd)

	w.Header().Set("Content-Type", "application/json")
	if err := json.NewEncoder(w).Encode(res); err != nil {
		http.Error(w, "Failed to encode response", http.StatusInternalServerError)
	}

}

// reportHolisticTrace emits the Langfuse trace for a completed holistic exam
// evaluation: a root trace tagged with the exam_session_id and four child agent
// spans (one per IELTS criterion). It mirrors the practice path's async,
// detached-context reporting so a slow or failing Langfuse never affects the
// caller.
func reportHolisticTrace(
	client *langfuse.Client,
	userID, examSessionID, transcript string,
	res agents.HolisticSwarmResult,
	swarmStart, swarmEnd time.Time,
) {
	if client == nil {
		return
	}

	go func() {
		detachedCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cancel()

		traceID := strings.ReplaceAll(uuid.New().String(), "-", "")

		events := make([]langfuse.IngestionEvent, 0, len(res.Dimensions)+1)
		events = append(events, langfuse.IngestionEvent{
			ID:        traceID,
			Type:      "trace",
			Timestamp: swarmStart,
			Body: langfuse.TraceBody{
				ID:        traceID,
				Name:      "speaking_exam_evaluation",
				UserID:    userID,
				SessionID: examSessionID,
				Metadata: map[string]any{
					"exam_session_id": examSessionID,
					"overall_band":    res.OverallBand,
					"partial":         res.Partial,
				},
			},
		})

		for _, criterion := range holisticCriteria {
			dim, ok := res.Dimensions[criterion]
			if !ok {
				continue
			}

			spanID := strings.ReplaceAll(uuid.New().String(), "-", "")[:16]
			metadata := map[string]any{
				"criterion":       criterion,
				"exam_session_id": examSessionID,
				"timed_out":       dim.TimedOut,
			}
			if !dim.TimedOut {
				metadata["band_score"] = dim.Band
			}

			events = append(events, langfuse.IngestionEvent{
				ID:        spanID,
				Type:      "generation",
				Timestamp: swarmStart,
				Body: langfuse.GenerationBody{
					ID:        spanID,
					TraceID:   traceID,
					Name:      criterion,
					StartTime: swarmStart,
					EndTime:   swarmEnd,
					Input:     transcript,
					Output:    dim.OverallFeedback,
					Metadata:  metadata,
				},
			})
		}

		if err := client.SendBatch(detachedCtx, events); err != nil {
			log.Error().Err(err).Str("exam_session_id", examSessionID).Msg("Failed to report holistic exam trace to Langfuse")
		}
	}()
}
