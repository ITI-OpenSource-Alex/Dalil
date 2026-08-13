package db

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"errors"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"
	"github.com/rs/zerolog/log"
)

// ErrSessionNotFound is returned by lookups that target a session id or
// share token that doesn't exist in the database.
var ErrSessionNotFound = errors.New("speaking session not found")

// SpeakingSession maps directly to our PostgreSQL table schema
type PgxPool interface {
	Exec(ctx context.Context, sql string, arguments ...any) (pgconn.CommandTag, error)
	Query(ctx context.Context, sql string, arguments ...any) (pgx.Rows, error)
	QueryRow(ctx context.Context, sql string, arguments ...any) pgx.Row
}
type SpeakingSession struct {
	ID             string          `json:"id"`
	UserID         string          `json:"user_id"`
	QuestionPrompt string          `json:"question_prompt"`
	QuestionType   string          `json:"question_type"`
	Transcript     string          `json:"transcript"`
	Evaluation     json.RawMessage `json:"evaluation"` // JSONB raw bytes
	// Nullable: a session where fewer than 3 of the 4 criteria completed has no
	// meaningful overall band, and 0.0 would be indistinguishable from a real
	// score of zero (GOA-032, BUG-040). Migration 003 drops the NOT NULL.
	OverallBand *float64  `json:"overall_band"`
	CreatedAt   time.Time `json:"created_at"`
}

// SpeakingExplanation is the immutable record of what a student was actually
// shown (SPEAK-EVAL-008).
//
// Written once at scoring time and never updated. Regenerating at read time
// would give different text for the same band on every visit -- the model is not
// deterministic, prompts change as they are tuned, and the rubric is versioned.
// A student told "band 6 because you paused five times" who returns to "band 6
// because your vocabulary was limited" has two reasons for one score and no way
// to know which was real.
type SpeakingExplanation struct {
	SessionID string          `json:"session_id"`
	Renderable json.RawMessage `json:"renderable"`

	RubricID      string `json:"rubric_id"`
	RubricVersion string `json:"rubric_version"`
	RubricSHA256  string `json:"rubric_sha256,omitempty"`
	ScorerVersion string `json:"scorer_version"`
	LLMModel      string `json:"llm_model,omitempty"`

	// Denormalised so a history listing can show "2 unverified" without parsing
	// every row's JSONB.
	ClaimCount    int `json:"claim_count"`
	WithheldCount int `json:"withheld_count"`

	CreatedAt time.Time `json:"created_at"`
}

// SpeakingSessionSummary is the lightweight projection used for session
// history listings — it deliberately omits the transcript/evaluation JSONB
// payloads so listing a user's history stays cheap regardless of how many
// sessions they have.
type SpeakingSessionSummary struct {
	ID             string    `json:"id"`
	QuestionPrompt string    `json:"question_prompt"`
	QuestionType   string    `json:"question_type"`
	OverallBand    *float64  `json:"overall_band"`
	CreatedAt      time.Time `json:"created_at"`
}

// Repository defines the contract for persisting and retrieving sessions

type Repository interface {
	Create(ctx context.Context, session *SpeakingSession) error
	ListByUser(ctx context.Context, userID string) ([]*SpeakingSessionSummary, error)
	GetByID(ctx context.Context, id string) (*SpeakingSession, error)
	CreateShareToken(ctx context.Context, sessionID string) (string, error)
	GetByShareToken(ctx context.Context, token string) (*SpeakingSession, error)
	DeleteByUser(ctx context.Context, userID string) (int64, error)
	DeleteOlderThan(ctx context.Context, cutoff time.Time) (int64, error)

	// SaveExplanation writes the explanation once. There is deliberately no
	// UpdateExplanation: see SpeakingExplanation for why an explanation must not
	// change after the student has read it.
	SaveExplanation(ctx context.Context, e *SpeakingExplanation) error
	GetExplanation(ctx context.Context, sessionID string) (*SpeakingExplanation, error)
}

type PostgresRepository struct {
	pool PgxPool
}

// NewPostgresRepository initializes our DB repo helper
func NewPostgresRepository(pool PgxPool) *PostgresRepository {
	return &PostgresRepository{pool: pool}
}

// Create inserts a session row into speaking_sessions database
func (r *PostgresRepository) Create(ctx context.Context, s *SpeakingSession) error {
	query := `
		INSERT INTO speaking_sessions (id, user_id, question_prompt, question_type, transcript, evaluation, overall_band, created_at)
		VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
	`
	_, err := r.pool.Exec(ctx, query,
		s.ID,
		s.UserID,
		s.QuestionPrompt,
		s.QuestionType,
		s.Transcript,
		s.Evaluation,
		s.OverallBand,
		s.CreatedAt,
	)
	if err != nil {
		log.Error().Err(err).Str("session_id", s.ID).Msg("Failed to insert speaking session into database")
		return err
	}
	log.Info().Str("session_id", s.ID).Msg("Successfully persisted speaking session to database")
	return nil
}

// ListByUser returns lightweight session summaries for a user, ordered from
// most to least recent.
func (r *PostgresRepository) ListByUser(ctx context.Context, userID string) ([]*SpeakingSessionSummary, error) {
	query := `
		SELECT id, question_prompt, question_type, overall_band, created_at
		FROM speaking_sessions
		WHERE user_id = $1
		ORDER BY created_at DESC
	`
	rows, err := r.pool.Query(ctx, query, userID)
	if err != nil {
		log.Error().Err(err).Str("user_id", userID).Msg("Failed to list speaking sessions")
		return nil, err
	}
	defer rows.Close()

	sessions := make([]*SpeakingSessionSummary, 0)
	for rows.Next() {
		s := &SpeakingSessionSummary{}
		if err := rows.Scan(&s.ID, &s.QuestionPrompt, &s.QuestionType, &s.OverallBand, &s.CreatedAt); err != nil {
			log.Error().Err(err).Str("user_id", userID).Msg("Failed to scan speaking session row")
			return nil, err
		}
		sessions = append(sessions, s)
	}
	if err := rows.Err(); err != nil {
		log.Error().Err(err).Str("user_id", userID).Msg("Error iterating speaking session rows")
		return nil, err
	}

	return sessions, nil
}

// GetByID returns the full session record, including transcript and
// evaluation, or ErrSessionNotFound if no session with that id exists.
func (r *PostgresRepository) GetByID(ctx context.Context, id string) (*SpeakingSession, error) {
	query := `
		SELECT id, user_id, question_prompt, question_type, transcript, evaluation, overall_band, created_at
		FROM speaking_sessions
		WHERE id = $1
	`
	s := &SpeakingSession{}
	err := r.pool.QueryRow(ctx, query, id).Scan(
		&s.ID, &s.UserID, &s.QuestionPrompt, &s.QuestionType, &s.Transcript, &s.Evaluation, &s.OverallBand, &s.CreatedAt,
	)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return nil, ErrSessionNotFound
		}
		log.Error().Err(err).Str("session_id", id).Msg("Failed to fetch speaking session")
		return nil, err
	}

	return s, nil
}

// CreateShareToken mints an opaque public share token for a session. It is
// idempotent: if the session already has a token, the existing token is
// returned unchanged rather than rotating it, so repeated "Share" clicks
// never invalidate a link that's already been copied/sent out.
func (r *PostgresRepository) CreateShareToken(ctx context.Context, sessionID string) (string, error) {
	candidate, err := generateShareToken()
	if err != nil {
		log.Error().Err(err).Str("session_id", sessionID).Msg("Failed to generate share token")
		return "", err
	}

	query := `
		UPDATE speaking_sessions
		SET share_token = COALESCE(share_token, $2)
		WHERE id = $1
		RETURNING share_token
	`
	var token string
	err = r.pool.QueryRow(ctx, query, sessionID, candidate).Scan(&token)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return "", ErrSessionNotFound
		}
		log.Error().Err(err).Str("session_id", sessionID).Msg("Failed to mint share token")
		return "", err
	}

	return token, nil
}

// GetByShareToken returns the full session record associated with a public
// share token, or ErrSessionNotFound if the token is unknown/invalid.
func (r *PostgresRepository) GetByShareToken(ctx context.Context, token string) (*SpeakingSession, error) {
	query := `
		SELECT id, user_id, question_prompt, question_type, transcript, evaluation, overall_band, created_at
		FROM speaking_sessions
		WHERE share_token = $1
	`
	s := &SpeakingSession{}
	err := r.pool.QueryRow(ctx, query, token).Scan(
		&s.ID, &s.UserID, &s.QuestionPrompt, &s.QuestionType, &s.Transcript, &s.Evaluation, &s.OverallBand, &s.CreatedAt,
	)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return nil, ErrSessionNotFound
		}
		log.Error().Err(err).Msg("Failed to fetch speaking session by share token")
		return nil, err
	}

	return s, nil
}

// DeleteByUser removes all speaking session records for a deleted account.
func (r *PostgresRepository) DeleteByUser(ctx context.Context, userID string) (int64, error) {
	result, err := r.pool.Exec(ctx, `DELETE FROM speaking_sessions WHERE user_id = $1`, userID)
	if err != nil {
		log.Error().Err(err).Str("user_id", userID).Msg("Failed to purge speaking sessions for deleted account")
		return 0, err
	}
	return result.RowsAffected(), nil
}

// DeleteOlderThan removes transcripts beyond the 365-day retention window.
func (r *PostgresRepository) DeleteOlderThan(ctx context.Context, cutoff time.Time) (int64, error) {
	result, err := r.pool.Exec(ctx, `DELETE FROM speaking_sessions WHERE created_at < $1`, cutoff)
	if err != nil {
		log.Error().Err(err).Time("cutoff", cutoff).Msg("Failed to purge expired speaking transcripts")
		return 0, err
	}
	return result.RowsAffected(), nil
}

// generateShareToken produces a 160-bit random hex token — unguessable and
// distinct from internal (sequential/UUID) session ids, so a public share
// link can't be used to enumerate other users' sessions.
func generateShareToken() (string, error) {
	buf := make([]byte, 20)
	if _, err := rand.Read(buf); err != nil {
		return "", err
	}
	return hex.EncodeToString(buf), nil
}



// SaveExplanation persists the explanation exactly as it was shown.
//
// ON CONFLICT DO NOTHING rather than DO UPDATE. A second write for the same
// session is a re-score or a retry, and the student has already read the first
// one -- silently replacing it is the regeneration this table exists to prevent.
// The insert is a no-op and the caller is told nothing changed, because nothing
// should.
func (r *PostgresRepository) SaveExplanation(ctx context.Context, e *SpeakingExplanation) error {
	query := `
		INSERT INTO speaking_explanations (
			session_id, renderable, rubric_id, rubric_version, rubric_sha256,
			scorer_version, llm_model, claim_count, withheld_count, created_at
		) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
		ON CONFLICT (session_id) DO NOTHING
	`
	_, err := r.pool.Exec(ctx, query,
		e.SessionID, e.Renderable, e.RubricID, e.RubricVersion, e.RubricSHA256,
		e.ScorerVersion, e.LLMModel, e.ClaimCount, e.WithheldCount, e.CreatedAt,
	)
	if err != nil {
		// Logged and returned, never swallowed: a session whose explanation
		// failed to persist will render nothing in history, and the cause has to
		// be visible now rather than inferred later from an empty page.
		log.Error().Err(err).Str("session_id", e.SessionID).
			Msg("Failed to persist speaking explanation")
		return err
	}
	return nil
}

// GetExplanation reads the stored explanation. Returns (nil, nil) when a session
// predates this table -- history renders the score without an explanation rather
// than fabricating one for an old session.
func (r *PostgresRepository) GetExplanation(ctx context.Context, sessionID string) (*SpeakingExplanation, error) {
	query := `
		SELECT session_id, renderable, rubric_id, rubric_version,
		       COALESCE(rubric_sha256, ''), scorer_version, COALESCE(llm_model, ''),
		       claim_count, withheld_count, created_at
		FROM speaking_explanations WHERE session_id = $1
	`
	var e SpeakingExplanation
	err := r.pool.QueryRow(ctx, query, sessionID).Scan(
		&e.SessionID, &e.Renderable, &e.RubricID, &e.RubricVersion, &e.RubricSHA256,
		&e.ScorerVersion, &e.LLMModel, &e.ClaimCount, &e.WithheldCount, &e.CreatedAt,
	)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return nil, nil
		}
		return nil, err
	}
	return &e, nil
}
