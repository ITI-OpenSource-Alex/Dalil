package db

import (
	"context"
	"encoding/json"
	"errors"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/pashagolub/pgxmock/v3"
)

func TestPostgresRepository_Create(t *testing.T) {
	// 1. Initialize pgxmock pool
	mock, err := pgxmock.NewPool()
	if err != nil {
		t.Fatalf("failed to create pgxmock pool: %v", err)
	}
	defer mock.Close()

	// 2. Initialize repository with the mock pool
	repo := NewPostgresRepository(mock)

	sessionID := uuid.New().String()
	createdAt := time.Now()
	session := &SpeakingSession{
		ID:             sessionID,
		UserID:         "user-123",
		QuestionPrompt: "Describe a book you read.",
		QuestionType:   "IELTS Part 2",
		Transcript:     "This is a book description...",
		Evaluation:     json.RawMessage(`{"fluency": {"band": 7.0}}`),
		OverallBand:    7.0,
		CreatedAt:      createdAt,
	}

	// 3. Define the expected SQL statement and arguments
	mock.ExpectExec("INSERT INTO speaking_sessions").
		WithArgs(
			session.ID,
			session.UserID,
			session.QuestionPrompt,
			session.QuestionType,
			session.Transcript,
			session.Evaluation,
			session.OverallBand,
			session.CreatedAt,
		).
		WillReturnResult(pgxmock.NewResult("INSERT", 1))

	// 4. Run the repository Create function
	err = repo.Create(context.Background(), session)
	if err != nil {
		t.Errorf("expected no error, got %v", err)
	}

	// 5. Ensure all database expectations were met
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Errorf("there were unfulfilled database expectations: %s", err)
	}
}

func TestPostgresRepository_ListByUser_ReturnsSummariesMostRecentFirst(t *testing.T) {
	mock, err := pgxmock.NewPool()
	if err != nil {
		t.Fatalf("failed to create pgxmock pool: %v", err)
	}
	defer mock.Close()

	repo := NewPostgresRepository(mock)

	newer := time.Now()
	older := newer.Add(-24 * time.Hour)

	rows := pgxmock.NewRows([]string{"id", "question_prompt", "question_type", "overall_band", "created_at"}).
		AddRow(uuid.New().String(), "Describe a memorable journey.", "part2", 7.5, newer).
		AddRow(uuid.New().String(), "Talk about your hometown.", "part1", 6.0, older)

	mock.ExpectQuery("SELECT id, question_prompt, question_type, overall_band, created_at").
		WithArgs("user-123").
		WillReturnRows(rows)

	sessions, err := repo.ListByUser(context.Background(), "user-123")
	if err != nil {
		t.Fatalf("expected no error, got %v", err)
	}
	if len(sessions) != 2 {
		t.Fatalf("expected 2 sessions, got %d", len(sessions))
	}
	if sessions[0].OverallBand != 7.5 || sessions[1].OverallBand != 6.0 {
		t.Errorf("unexpected session ordering/content: %+v", sessions)
	}

	if err := mock.ExpectationsWereMet(); err != nil {
		t.Errorf("there were unfulfilled database expectations: %s", err)
	}
}

func TestPostgresRepository_ListByUser_EmptyReturnsEmptySlice(t *testing.T) {
	mock, err := pgxmock.NewPool()
	if err != nil {
		t.Fatalf("failed to create pgxmock pool: %v", err)
	}
	defer mock.Close()

	repo := NewPostgresRepository(mock)

	rows := pgxmock.NewRows([]string{"id", "question_prompt", "question_type", "overall_band", "created_at"})

	mock.ExpectQuery("SELECT id, question_prompt, question_type, overall_band, created_at").
		WithArgs("user-with-no-history").
		WillReturnRows(rows)

	sessions, err := repo.ListByUser(context.Background(), "user-with-no-history")
	if err != nil {
		t.Fatalf("expected no error, got %v", err)
	}
	if sessions == nil {
		t.Fatal("expected an empty slice, got nil")
	}
	if len(sessions) != 0 {
		t.Errorf("expected 0 sessions, got %d", len(sessions))
	}

	if err := mock.ExpectationsWereMet(); err != nil {
		t.Errorf("there were unfulfilled database expectations: %s", err)
	}
}

func TestPostgresRepository_GetByID_Success(t *testing.T) {
	mock, err := pgxmock.NewPool()
	if err != nil {
		t.Fatalf("failed to create pgxmock pool: %v", err)
	}
	defer mock.Close()

	repo := NewPostgresRepository(mock)

	sessionID := uuid.New().String()
	createdAt := time.Now()

	rows := pgxmock.NewRows([]string{
		"id", "user_id", "question_prompt", "question_type", "transcript", "evaluation", "overall_band", "created_at",
	}).AddRow(
		sessionID, "user-123", "Describe a book you read.", "part2", "This is a book description...",
		json.RawMessage(`{"Fluency and Coherence": {"band": 7.0}}`), 7.0, createdAt,
	)

	mock.ExpectQuery("SELECT id, user_id, question_prompt, question_type, transcript, evaluation, overall_band, created_at").
		WithArgs(sessionID).
		WillReturnRows(rows)

	session, err := repo.GetByID(context.Background(), sessionID)
	if err != nil {
		t.Fatalf("expected no error, got %v", err)
	}
	if session.ID != sessionID || session.UserID != "user-123" || session.OverallBand != 7.0 {
		t.Errorf("unexpected session content: %+v", session)
	}

	if err := mock.ExpectationsWereMet(); err != nil {
		t.Errorf("there were unfulfilled database expectations: %s", err)
	}
}

func TestPostgresRepository_GetByID_NotFound(t *testing.T) {
	mock, err := pgxmock.NewPool()
	if err != nil {
		t.Fatalf("failed to create pgxmock pool: %v", err)
	}
	defer mock.Close()

	repo := NewPostgresRepository(mock)

	missingID := uuid.New().String()

	mock.ExpectQuery("SELECT id, user_id, question_prompt, question_type, transcript, evaluation, overall_band, created_at").
		WithArgs(missingID).
		WillReturnError(pgx.ErrNoRows)

	_, err = repo.GetByID(context.Background(), missingID)
	if !errors.Is(err, ErrSessionNotFound) {
		t.Fatalf("expected ErrSessionNotFound, got %v", err)
	}

	if err := mock.ExpectationsWereMet(); err != nil {
		t.Errorf("there were unfulfilled database expectations: %s", err)
	}
}

func TestPostgresRepository_CreateShareToken_MintsTokenForUnsharedSession(t *testing.T) {
	mock, err := pgxmock.NewPool()
	if err != nil {
		t.Fatalf("failed to create pgxmock pool: %v", err)
	}
	defer mock.Close()

	repo := NewPostgresRepository(mock)

	sessionID := uuid.New().String()

	// The repository generates a random candidate token client-side and lets
	// the DB decide (via COALESCE) whether to keep an existing one instead.
	// pgxmock can't echo back the captured arg, so this test just asserts on
	// the resulting behavior: a non-empty token comes back and no error occurs.
	mock.ExpectQuery("UPDATE speaking_sessions").
		WithArgs(sessionID, pgxmock.AnyArg()).
		WillReturnRows(pgxmock.NewRows([]string{"share_token"}).AddRow("freshly-minted-token"))

	token, err := repo.CreateShareToken(context.Background(), sessionID)
	if err != nil {
		t.Fatalf("expected no error, got %v", err)
	}
	if token == "" {
		t.Error("expected a non-empty share token")
	}

	if err := mock.ExpectationsWereMet(); err != nil {
		t.Errorf("there were unfulfilled database expectations: %s", err)
	}
}

func TestPostgresRepository_CreateShareToken_IsIdempotentForAlreadySharedSession(t *testing.T) {
	mock, err := pgxmock.NewPool()
	if err != nil {
		t.Fatalf("failed to create pgxmock pool: %v", err)
	}
	defer mock.Close()

	repo := NewPostgresRepository(mock)

	sessionID := uuid.New().String()
	existingToken := "existing-token-1234567890"

	mock.ExpectQuery("UPDATE speaking_sessions").
		WithArgs(sessionID, pgxmock.AnyArg()).
		WillReturnRows(pgxmock.NewRows([]string{"share_token"}).AddRow(existingToken))

	token, err := repo.CreateShareToken(context.Background(), sessionID)
	if err != nil {
		t.Fatalf("expected no error, got %v", err)
	}
	if token != existingToken {
		t.Errorf("expected the pre-existing token %q to be returned unchanged, got %q", existingToken, token)
	}

	if err := mock.ExpectationsWereMet(); err != nil {
		t.Errorf("there were unfulfilled database expectations: %s", err)
	}
}

func TestPostgresRepository_CreateShareToken_SessionNotFound(t *testing.T) {
	mock, err := pgxmock.NewPool()
	if err != nil {
		t.Fatalf("failed to create pgxmock pool: %v", err)
	}
	defer mock.Close()

	repo := NewPostgresRepository(mock)

	missingID := uuid.New().String()

	mock.ExpectQuery("UPDATE speaking_sessions").
		WithArgs(missingID, pgxmock.AnyArg()).
		WillReturnError(pgx.ErrNoRows)

	_, err = repo.CreateShareToken(context.Background(), missingID)
	if !errors.Is(err, ErrSessionNotFound) {
		t.Fatalf("expected ErrSessionNotFound, got %v", err)
	}

	if err := mock.ExpectationsWereMet(); err != nil {
		t.Errorf("there were unfulfilled database expectations: %s", err)
	}
}

func TestPostgresRepository_GetByShareToken_Success(t *testing.T) {
	mock, err := pgxmock.NewPool()
	if err != nil {
		t.Fatalf("failed to create pgxmock pool: %v", err)
	}
	defer mock.Close()

	repo := NewPostgresRepository(mock)

	sessionID := uuid.New().String()
	token := "abc123def456"
	createdAt := time.Now()

	rows := pgxmock.NewRows([]string{
		"id", "user_id", "question_prompt", "question_type", "transcript", "evaluation", "overall_band", "created_at",
	}).AddRow(
		sessionID, "user-123", "Describe a book you read.", "part2", "This is a book description...",
		json.RawMessage(`{"Fluency and Coherence": {"band": 7.0}}`), 7.0, createdAt,
	)

	mock.ExpectQuery("SELECT id, user_id, question_prompt, question_type, transcript, evaluation, overall_band, created_at").
		WithArgs(token).
		WillReturnRows(rows)

	session, err := repo.GetByShareToken(context.Background(), token)
	if err != nil {
		t.Fatalf("expected no error, got %v", err)
	}
	if session.ID != sessionID {
		t.Errorf("unexpected session id: %q", session.ID)
	}

	if err := mock.ExpectationsWereMet(); err != nil {
		t.Errorf("there were unfulfilled database expectations: %s", err)
	}
}

func TestPostgresRepository_GetByShareToken_NotFound(t *testing.T) {
	mock, err := pgxmock.NewPool()
	if err != nil {
		t.Fatalf("failed to create pgxmock pool: %v", err)
	}
	defer mock.Close()

	repo := NewPostgresRepository(mock)

	mock.ExpectQuery("SELECT id, user_id, question_prompt, question_type, transcript, evaluation, overall_band, created_at").
		WithArgs("unknown-token").
		WillReturnError(pgx.ErrNoRows)

	_, err = repo.GetByShareToken(context.Background(), "unknown-token")
	if !errors.Is(err, ErrSessionNotFound) {
		t.Fatalf("expected ErrSessionNotFound, got %v", err)
	}

	if err := mock.ExpectationsWereMet(); err != nil {
		t.Errorf("there were unfulfilled database expectations: %s", err)
	}
}
