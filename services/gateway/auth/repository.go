package auth

import (
	"context"
	"database/sql"
	"errors"
	"time"
)

var (
	ErrTokenNotFound = errors.New("token not found or already revoked")
)

type RefreshToken struct {
	ID         string
	TokenHash  string
	UserID     string
	ExpiresAt  time.Time
	RevokedAt  *time.Time
	CreatedAt  time.Time
	DeviceHint *string
}

type RefreshTokenRepository struct {
	db *sql.DB
}

func NewRefreshTokenRepository(db *sql.DB) *RefreshTokenRepository {
	return &RefreshTokenRepository{db: db}
}

// Create inserts a new refresh token and returns the generated UUID.
func (r *RefreshTokenRepository) Create(ctx context.Context, userID string, tokenHash string, expiresAt time.Time, deviceHint *string) (string, error) {
	query := `
	
		INSERT INTO refresh_tokens (token_hash, user_id, expires_at, device_hint, created_at)
		VALUES ($1, $2, $3, $4, NOW())
		RETURNING id
	
	`

	var id string

	err := r.db.QueryRowContext(ctx, query, tokenHash, userID, expiresAt, deviceHint).Scan(&id)
	if err != nil {
		return "", err
	}
	return id, nil
}

// FindByID retrieves a refresh token.
func (r *RefreshTokenRepository) FindByID(ctx context.Context, id string) (*RefreshToken, error) {
	query := `

	SELECT id, token_hash, user_id, expires_at, revoked_at, created_at, device_hint
		FROM refresh_tokens
		WHERE id = $1
	
	`

	var token RefreshToken
	err := r.db.QueryRowContext(ctx, query, id).Scan(&token.ID,
		&token.TokenHash,
		&token.UserID,
		&token.ExpiresAt,
		&token.RevokedAt,
		&token.CreatedAt,
		&token.DeviceHint)

	if err != nil {
		return nil, err
	}
	return &token, nil
}

// Revoke invalidates a specific refresh token by ID (used on logout and token rotation).
func (r *RefreshTokenRepository) Revoke(ctx context.Context, id string) error {
	query := `
		UPDATE refresh_tokens
		SET revoked_at = NOW()
		WHERE id = $1 AND revoked_at IS NULL
	`
	result, err := r.db.ExecContext(ctx, query, id)
	if err != nil {
		return err
	}
	n, err := result.RowsAffected()
	if err != nil {
		return err
	}
	if n == 0 {
		return ErrTokenNotFound
	}
	return nil
}

// RevokeAll invalidates all active sessions for a user (used on logout-all and replay attacks).

func (r *RefreshTokenRepository) RevokeAll(ctx context.Context, userID string) error {
	query := `
		UPDATE refresh_tokens
		SET revoked_at = NOW()
		WHERE user_id = $1 AND revoked_at IS NULL
	`
	_, err := r.db.ExecContext(ctx, query, userID)
	return err
}
