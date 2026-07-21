package db

import (
	"context"
	"encoding/json"
	"time"

	"github.com/jackc/pgx/v5/pgconn"
	"github.com/rs/zerolog/log"
)

// SpeakingSession maps directly to our PostgreSQL table schema
type PgxPool interface {
	Exec(ctx context.Context, sql string, arguments ...any) (pgconn.CommandTag, error)
}
type SpeakingSession struct {
	ID             string          `json:"id"`
	UserID         string          `json:"user_id"`
	QuestionPrompt string          `json:"question_prompt"`
	QuestionType   string          `json:"question_type"`
	Transcript     string          `json:"transcript"`
	Evaluation     json.RawMessage `json:"evaluation"` // JSONB raw bytes
	OverallBand    float64         `json:"overall_band"`
	CreatedAt      time.Time       `json:"created_at"`
}

// Repository defines the contract for persisting sessions

type Repository interface {
	Create(ctx context.Context, session *SpeakingSession) error
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
