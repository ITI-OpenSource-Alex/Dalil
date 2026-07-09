package auth

import (
	"context"
	"errors"
	"strings"

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
