package db

import (
	"context"
	"encoding/json"
	"errors"
	"time"

	"github.com/ITI-OpenSource-Alex/GOA/services/speaking/internal/interview"
	"github.com/jackc/pgx/v5"
)

type InterviewSession struct {
	ID          string
	UserID      string
	Status      string
	BankVersion string
	BankSHA256  string
	CueID       string
	VoiceID     string
	AudioFormat string
	Selection   interview.Selection
	Snapshot    interview.Snapshot
	Partial     bool
	CreatedAt   time.Time
	UpdatedAt   time.Time
}

func (r *PostgresRepository) CreateInterview(ctx context.Context, session InterviewSession) error {
	selection, err := json.Marshal(session.Selection)
	if err != nil {
		return err
	}
	snapshot, err := json.Marshal(session.Snapshot)
	if err != nil {
		return err
	}
	_, err = r.pool.Exec(ctx, `
		INSERT INTO speaking_interview_sessions (
			id, user_id, status, bank_version, bank_sha256, cue_id, voice_id,
			audio_format, selection, snapshot, partial, created_at, updated_at
		) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$12)
	`, session.ID, session.UserID, session.Status, session.BankVersion,
		session.BankSHA256, session.CueID, session.VoiceID, session.AudioFormat,
		selection, snapshot, session.Partial, session.CreatedAt)
	return err
}

func (r *PostgresRepository) SaveInterviewTurn(ctx context.Context, sessionID string, turn interview.Turn) error {
	words, err := json.Marshal(turn.Words)
	if err != nil {
		return err
	}
	_, err = r.pool.Exec(ctx, `
		INSERT INTO speaking_interview_turns (
			session_id, turn_id, part, question_id, speaker, text, audio_ref,
			words, start_s, end_s
		) VALUES ($1,$2,$3,$4,$5,$6,NULLIF($7,''),$8,$9,$10)
		ON CONFLICT (session_id, turn_id) DO UPDATE SET
			part=EXCLUDED.part, question_id=EXCLUDED.question_id,
			speaker=EXCLUDED.speaker, text=EXCLUDED.text,
			audio_ref=EXCLUDED.audio_ref, words=EXCLUDED.words,
			start_s=EXCLUDED.start_s, end_s=EXCLUDED.end_s
	`, sessionID, turn.TurnID, turn.Part, turn.QuestionID, turn.Speaker,
		turn.Text, turn.AudioRef, words, turn.StartS, turn.EndS)
	return err
}

func (r *PostgresRepository) SaveInterviewProgress(ctx context.Context, sessionID string, snapshot interview.Snapshot, status string, partial bool) error {
	payload, err := json.Marshal(snapshot)
	if err != nil {
		return err
	}
	result, err := r.pool.Exec(ctx, `
		UPDATE speaking_interview_sessions
		SET snapshot=$2, status=$3, partial=$4, updated_at=NOW()
		WHERE id=$1
	`, sessionID, payload, status, partial)
	if err != nil {
		return err
	}
	if result.RowsAffected() == 0 {
		return ErrSessionNotFound
	}
	return nil
}

func (r *PostgresRepository) LoadInterview(ctx context.Context, sessionID, userID string) (*InterviewSession, error) {
	var session InterviewSession
	var selectionJSON, snapshotJSON []byte
	err := r.pool.QueryRow(ctx, `
		SELECT id, user_id, status, bank_version, bank_sha256, cue_id, voice_id,
		       audio_format, selection, snapshot, partial, created_at, updated_at
		FROM speaking_interview_sessions WHERE id=$1 AND user_id=$2
	`, sessionID, userID).Scan(
		&session.ID, &session.UserID, &session.Status, &session.BankVersion,
		&session.BankSHA256, &session.CueID, &session.VoiceID, &session.AudioFormat,
		&selectionJSON, &snapshotJSON, &session.Partial, &session.CreatedAt, &session.UpdatedAt,
	)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return nil, ErrSessionNotFound
		}
		return nil, err
	}
	if err := json.Unmarshal(selectionJSON, &session.Selection); err != nil {
		return nil, err
	}
	if err := json.Unmarshal(snapshotJSON, &session.Snapshot); err != nil {
		return nil, err
	}
	return &session, nil
}

func (r *PostgresRepository) RecentInterviewCueIDs(ctx context.Context, userID string, limit int) ([]string, error) {
	if limit <= 0 {
		return nil, nil
	}
	rows, err := r.pool.Query(ctx, `
		SELECT cue_id FROM speaking_interview_sessions
		WHERE user_id=$1 ORDER BY created_at DESC LIMIT $2
	`, userID, limit)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	ids := make([]string, 0, limit)
	for rows.Next() {
		var id string
		if err := rows.Scan(&id); err != nil {
			return nil, err
		}
		ids = append(ids, id)
	}
	return ids, rows.Err()
}

func (r *PostgresRepository) DeleteInterviewsByUser(ctx context.Context, userID string) (int64, error) {
	result, err := r.pool.Exec(ctx, `DELETE FROM speaking_interview_sessions WHERE user_id=$1`, userID)
	if err != nil {
		return 0, err
	}
	return result.RowsAffected(), nil
}

func (r *PostgresRepository) DeleteInterviewsOlderThan(ctx context.Context, cutoff time.Time) (int64, error) {
	result, err := r.pool.Exec(ctx, `DELETE FROM speaking_interview_sessions WHERE created_at<$1`, cutoff)
	if err != nil {
		return 0, err
	}
	return result.RowsAffected(), nil
}
