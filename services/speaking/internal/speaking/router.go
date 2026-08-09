// internal/speaking/router.go
package speaking

import (
	"net/http"
	"time"

	"github.com/ITI-OpenSource-Alex/GOA/services/speaking/agents"
	"github.com/ITI-OpenSource-Alex/GOA/services/speaking/db"
	"github.com/ITI-OpenSource-Alex/GOA/services/speaking/internal/interview"
	"github.com/ITI-OpenSource-Alex/GOA/services/speaking/langfuse"
	"github.com/prometheus/client_golang/prometheus/promhttp"
)

// RouterDeps bundles everything the HTTP layer needs. Grouping them keeps
// NewRouter's signature stable as handlers gain dependencies, and lets tests
// build the production router with stubs for the parts they don't exercise.
type RouterDeps struct {
	Config          *Config
	Repo            db.Repository
	PracticeLLM     agents.LLMClient
	ExamLLM         agents.LLMClient
	TTS             TTSClient
	Langfuse        *langfuse.Client
	InterviewStore  InterviewStore
	Interviewer     interview.FollowupGenerator
	InterviewBank   *interview.Bank
	Transcriber     TurnTranscriber
	ExaminerVoice   ExaminerVoice
	InterviewTiming interview.Timing
	Now             func() time.Time
	Part3MaxTurns   int
}

// preflight answers CORS preflight requests. WithCORS short-circuits every
// OPTIONS request with 204 plus the CORS headers, so the wrapped handler is
// never actually invoked — it exists only to satisfy the signature.
func preflight() http.HandlerFunc {
	return WithCORS(func(http.ResponseWriter, *http.Request) {})
}

// NewRouter builds the service's HTTP router. main() serves exactly what this
// returns, so an integration test can construct the real routing table without
// starting a listener or touching the global DefaultServeMux.
//
// Registration order does not matter to net/http — patterns are matched by
// specificity, not by declaration order — but conflicting patterns panic at
// registration time, so this function is deliberately the single place where
// every route is declared.
func NewRouter(deps RouterDeps) *http.ServeMux {
	mux := http.NewServeMux()

	mux.HandleFunc("GET /health", func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"status":"healthy"}`))
	})

	store := deps.InterviewStore
	if store == nil {
		store, _ = deps.Repo.(InterviewStore)
	}
	bank := deps.InterviewBank
	if bank == nil {
		bank, _ = interview.LoadDefaultBank()
	}
	transcriber := deps.Transcriber
	if transcriber == nil && deps.Config != nil {
		transcriber = NewSpeechTurnTranscriber(deps.Config.SpeechServiceURL)
	}
	voice := deps.ExaminerVoice
	if voice == nil && deps.TTS != nil {
		voice = NewCachedExaminerVoice(deps.TTS)
	}
	var followups *interview.FollowupEngine
	if deps.Interviewer != nil {
		followups = &interview.FollowupEngine{
			Generator: deps.Interviewer, TopicChecker: SeedTopicChecker{},
			Policy: interview.DefaultFollowupPolicy(), Timeout: interviewerTimeout,
		}
	}

	// Protocol v3 is the production endpoint. The legacy monologue handler is
	// retained only on /ws/v2 for controlled rollback and its regression suite;
	// a v2 frame sent to /ws receives a typed protocol refusal.
	mux.HandleFunc("/ws", func(w http.ResponseWriter, r *http.Request) {
		HandleInterviewWebSocket(w, r, InterviewSocketDeps{
			Config: deps.Config, Sessions: deps.Repo, Store: store,
			ScoringLLM: deps.PracticeLLM, Transcriber: transcriber, Voice: voice,
			Bank: bank, Followups: followups, Timing: deps.InterviewTiming,
			Now: deps.Now, Part3MaxTurn: deps.Part3MaxTurns,
		})
	})
	mux.HandleFunc("/ws/v2", func(w http.ResponseWriter, r *http.Request) {
		HandleWebSocket(w, r, deps.Config, deps.Repo, deps.PracticeLLM, deps.TTS, deps.Langfuse)
	})

	mux.HandleFunc("/internal/evaluate/holistic", func(w http.ResponseWriter, r *http.Request) {
		HandleHolisticEvaluation(w, r, deps.Config, deps.ExamLLM, deps.Langfuse)
	})

	// Session history / share endpoints — called directly by the frontend
	// browser client (same direct-connection pattern as /ws), so each one is
	// CORS-wrapped.
	mux.HandleFunc("GET /sessions", WithCORS(func(w http.ResponseWriter, r *http.Request) {
		HandleListSessions(w, r, deps.Repo)
	}))

	mux.HandleFunc("GET /sessions/{id}", WithCORS(func(w http.ResponseWriter, r *http.Request) {
		HandleGetSession(w, r, deps.Repo)
	}))

	mux.HandleFunc("POST /sessions/{id}/share", WithCORS(func(w http.ResponseWriter, r *http.Request) {
		HandleCreateShareLink(w, r, deps.Repo)
	}))

	mux.HandleFunc("GET /sessions/public/{token}", WithCORS(func(w http.ResponseWriter, r *http.Request) {
		HandleGetPublicSession(w, r, deps.Repo)
	}))

	// Preflight is served by two non-overlapping patterns: an exact match for
	// the collection, and a trailing-wildcard for everything beneath it.
	//
	// Declaring one OPTIONS pattern per route instead panics on startup:
	// "OPTIONS /sessions/{id}/share" and "OPTIONS /sessions/public/{token}"
	// both match "/sessions/public/share" and neither is more specific, which
	// net/http rejects as an ambiguous registration. A single wildcard has no
	// sibling to be ambiguous against, and it keeps preflight working for any
	// /sessions subpath added later. See TestNewRouter_* for the regression
	// guard.
	mux.HandleFunc("OPTIONS /sessions", preflight())
	mux.HandleFunc("OPTIONS /sessions/{path...}", preflight())

	mux.Handle("/metrics", promhttp.Handler())

	return mux
}
