package auth

import (
	"context"
	"database/sql"
	"errors"
	"strings"

	"golang.org/x/crypto/bcrypt"
)

var ErrInvalidCredentials = errors.New("invalid credentials")

type User struct {
	ID    string
	Email string
}

type CredentialValidator interface {
	Validate(ctx context.Context, email string, password string) (User, error)
}

type StaticCredentialValidator struct{}

func (StaticCredentialValidator) Validate(ctx context.Context, email string, password string) (User, error) {
	normalizedEmail := strings.ToLower(strings.TrimSpace(email))
	if normalizedEmail != "user@example.com" || password != "password" {
		return User{}, ErrInvalidCredentials
	}

	return User{
		ID:    "00000000-0000-0000-0000-000000000001",
		Email: normalizedEmail,
	}, nil
}

type DatabaseCredentialValidator struct {
	db *sql.DB
}

// NewDatabaseCredentialValidator initializes a new DB validator instance.
func NewDatabaseCredentialValidator(db *sql.DB) *DatabaseCredentialValidator {
	return &DatabaseCredentialValidator{db: db}
}

// Validate queries user_db to authenticate the user.
func (v *DatabaseCredentialValidator) Validate(ctx context.Context, email string, password string) (User, error) {
	normalizedEmail := strings.ToLower(strings.TrimSpace(email))
	if normalizedEmail == "" || password == "" {
		return User{}, ErrInvalidCredentials
	}

	var user User
	var passwordHash string

	query := `SELECT id, email, "passwordHash" FROM users WHERE LOWER(email) = $1`
	err := v.db.QueryRowContext(ctx, query, normalizedEmail).Scan(&user.ID, &user.Email, &passwordHash)
	if err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return User{}, ErrInvalidCredentials
		}
		return User{}, err
	}

	// Verify the password using bcrypt
	err = bcrypt.CompareHashAndPassword([]byte(passwordHash), []byte(password))
	if err != nil {
		return User{}, ErrInvalidCredentials
	}

	return user, nil
}
