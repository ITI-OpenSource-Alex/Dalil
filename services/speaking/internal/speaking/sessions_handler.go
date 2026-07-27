// internal/speaking/sessions_handler.go
package speaking

import (
	"encoding/json"
	"errors"
	"net/http"
	"time"

	"github.com/ITI-OpenSource-Alex/GOA/services/speaking/db"
	"github.com/google/uuid"
	"github.com/rs/zerolog/log"
)

// sessionSummaryResponse is the JSON shape returned by GET /sessions.
type sessionSummaryResponse struct {
	ID             string    `json:"id"`
	QuestionPrompt string    `json:"question_prompt"`
	QuestionType   string    `json:"question_type"`
	OverallBand    float64   `json:"overall_band"`
	CreatedAt      time.Time `json:"created_at"`
}

// sessionDetailResponse is the JSON shape returned by GET /sessions/{id} and
// GET /sessions/public/{token}. It deliberately omits UserID (and any other
// account-identifying field) so the same shape is safe to reuse for the
// public, unauthenticated share response.
type sessionDetailResponse struct {
	ID             string          `json:"id"`
	QuestionPrompt string          `json:"question_prompt"`
	QuestionType   string          `json:"question_type"`
	Transcript     string          `json:"transcript"`
	Evaluation     json.RawMessage `json:"evaluation"`
	OverallBand    float64         `json:"overall_band"`
	CreatedAt      time.Time       `json:"created_at"`
}

func toSummaryResponses(sessions []*db.SpeakingSessionSummary) []sessionSummaryResponse {
	out := make([]sessionSummaryResponse, 0, len(sessions))
	for _, s := range sessions {
		out = append(out, sessionSummaryResponse{
			ID:             s.ID,
			QuestionPrompt: s.QuestionPrompt,
			QuestionType:   s.QuestionType,
			OverallBand:    s.OverallBand,
			CreatedAt:      s.CreatedAt,
		})
	}
	return out
}

func toDetailResponse(s *db.SpeakingSession) sessionDetailResponse {
	return sessionDetailResponse{
		ID:             s.ID,
		QuestionPrompt: s.QuestionPrompt,
		QuestionType:   s.QuestionType,
		Transcript:     s.Transcript,
		Evaluation:     s.Evaluation,
		OverallBand:    s.OverallBand,
		CreatedAt:      s.CreatedAt,
	}
}

// validSessionID reports whether a path-supplied session id is a well-formed
// UUID, writing the error response itself when it is not.
//
// speaking_sessions.id is a Postgres uuid column, so a malformed id fails at
// the type cast (SQLSTATE 22P02) rather than matching zero rows. That error
// is indistinguishable from a genuine database failure by the time it reaches
// the handler, so it used to surface as a 500 for what is really bad client
// input. Rejecting it up front keeps the query from running at all.
//
// A syntactically invalid id can never name a real session, so it is reported
// as 404 — the same answer already given for an unknown id and for one owned
// by another user. Keeping all three indistinguishable is deliberate: it stops
// the endpoint from being used to probe which session ids exist.
func validSessionID(w http.ResponseWriter, id string) bool {
	if _, err := uuid.Parse(id); err != nil {
		http.Error(w, "Session not found", http.StatusNotFound)
		return false
	}
	return true
}

func writeJSON(w http.ResponseWriter, status int, payload any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	if err := json.NewEncoder(w).Encode(payload); err != nil {
		log.Error().Err(err).Msg("Failed to encode JSON response")
	}
}

// HandleListSessions handles GET /sessions?userId=... — returns a user's
// speaking session history, most recent first.
func HandleListSessions(w http.ResponseWriter, r *http.Request, dbRepo db.Repository) {
	userID := r.URL.Query().Get("userId")
	if userID == "" {
		http.Error(w, "userId query parameter is required", http.StatusBadRequest)
		return
	}

	sessions, err := dbRepo.ListByUser(r.Context(), userID)
	if err != nil {
		log.Error().Err(err).Str("user_id", userID).Msg("Failed to list speaking sessions")
		http.Error(w, "Failed to load session history", http.StatusInternalServerError)
		return
	}

	writeJSON(w, http.StatusOK, toSummaryResponses(sessions))
}

// HandleGetSession handles GET /sessions/{id} — returns the full evaluation
// breakdown and transcript for a single session. When a userId query param
// is supplied, the session is scoped to that user; a session that exists
// but belongs to someone else is reported as not-found rather than
// forbidden, so the endpoint can't be used to enumerate other users' ids.
func HandleGetSession(w http.ResponseWriter, r *http.Request, dbRepo db.Repository) {
	id := r.PathValue("id")
	if id == "" {
		http.Error(w, "session id is required", http.StatusBadRequest)
		return
	}
	if !validSessionID(w, id) {
		return
	}

	userID := r.URL.Query().Get("userId")

	session, err := dbRepo.GetByID(r.Context(), id)
	if err != nil {
		if errors.Is(err, db.ErrSessionNotFound) {
			http.Error(w, "Session not found", http.StatusNotFound)
			return
		}
		log.Error().Err(err).Str("session_id", id).Msg("Failed to fetch speaking session")
		http.Error(w, "Failed to load session", http.StatusInternalServerError)
		return
	}

	if userID != "" && session.UserID != userID {
		http.Error(w, "Session not found", http.StatusNotFound)
		return
	}

	writeJSON(w, http.StatusOK, toDetailResponse(session))
}

// HandleCreateShareLink handles POST /sessions/{id}/share — mints (or, if
// one already exists, returns) the public share token for a session.
func HandleCreateShareLink(w http.ResponseWriter, r *http.Request, dbRepo db.Repository) {
	id := r.PathValue("id")
	if id == "" {
		http.Error(w, "session id is required", http.StatusBadRequest)
		return
	}
	if !validSessionID(w, id) {
		return
	}

	token, err := dbRepo.CreateShareToken(r.Context(), id)
	if err != nil {
		if errors.Is(err, db.ErrSessionNotFound) {
			http.Error(w, "Session not found", http.StatusNotFound)
			return
		}
		log.Error().Err(err).Str("session_id", id).Msg("Failed to create share link")
		http.Error(w, "Failed to create share link", http.StatusInternalServerError)
		return
	}

	writeJSON(w, http.StatusOK, map[string]string{"share_token": token})
}

// HandleGetPublicSession handles GET /sessions/public/{token} — an
// unauthenticated read of a shared session, addressed only by its opaque
// share token (never by the internal session id).
func HandleGetPublicSession(w http.ResponseWriter, r *http.Request, dbRepo db.Repository) {
	token := r.PathValue("token")
	if token == "" {
		http.Error(w, "share token is required", http.StatusBadRequest)
		return
	}

	session, err := dbRepo.GetByShareToken(r.Context(), token)
	if err != nil {
		if errors.Is(err, db.ErrSessionNotFound) {
			http.Error(w, "Shared session not found", http.StatusNotFound)
			return
		}
		log.Error().Err(err).Msg("Failed to fetch shared speaking session")
		http.Error(w, "Failed to load shared session", http.StatusInternalServerError)
		return
	}

	writeJSON(w, http.StatusOK, toDetailResponse(session))
}
