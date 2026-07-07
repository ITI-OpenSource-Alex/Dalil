package db

import (
	"context"
	"encoding/json"
	"testing"
	"time"

	"github.com/google/uuid"
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
