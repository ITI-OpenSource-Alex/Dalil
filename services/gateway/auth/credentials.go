package auth

import (
	"errors"
	"strings"
)

var ErrInvalidCredentials = errors.New("invalid credentials")

type User struct {
	ID    string
	Email string
}

type CredentialValidator interface {
	Validate(email string, password string) (User, error)
}

type StaticCredentialValidator struct{}

func (StaticCredentialValidator) Validate(email string, password string) (User, error) {
	normalizedEmail := strings.ToLower(strings.TrimSpace(email))
	if normalizedEmail != "user@example.com" || password != "password" {
		return User{}, ErrInvalidCredentials
	}

	return User{
		ID:    "user-1",
		Email: normalizedEmail,
	}, nil
}
