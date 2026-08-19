package auth

import (
	"errors"
	"time"

	"github.com/golang-jwt/jwt/v5"
	"github.com/google/uuid"
)

const (
	AccessTokenType  = "access"
	RefreshTokenType = "refresh"
)

var (
	ErrInvalidToken   = errors.New("invalid token")
	ErrExpiredToken   = errors.New("expired token")
	ErrWrongTokenType = errors.New("wrong token type")
)

type Claims struct {
	Email     string `json:"email,omitempty"`
	TokenType string `json:"token_type,omitempty"`
	jwt.RegisteredClaims
}

type TokenService struct {
	secret          []byte
	accessTokenTTL  time.Duration
	refreshTokenTTL time.Duration
}

// JWT validates access tokens. It checks both HTTP headers and cookies,
// and cross-checks the token's jti with the Redis blacklist cache.

func NewTokenService(secret string, accessTokenTTL time.Duration, refreshTokenTTL time.Duration) *TokenService {
	return &TokenService{
		secret:          []byte(secret),
		accessTokenTTL:  accessTokenTTL,
		refreshTokenTTL: refreshTokenTTL,
	}
}

func (s *TokenService) AccessTokenTTL() time.Duration {
	return s.accessTokenTTL
}

func (s *TokenService) NewAccessToken(user User) (string, error) {
	return s.sign(user, AccessTokenType, s.accessTokenTTL)
}

func (s *TokenService) NewRefreshToken(user User) (string, error) {
	return s.sign(user, RefreshTokenType, s.refreshTokenTTL)
}

func (s *TokenService) ParseAccessToken(tokenString string) (*Claims, error) {
	return s.parse(tokenString, AccessTokenType)
}

func (s *TokenService) ParseRefreshToken(tokenString string) (*Claims, error) {
	return s.parse(tokenString, RefreshTokenType)
}

func (s *TokenService) sign(user User, tokenType string, ttl time.Duration) (string, error) {
	now := time.Now().UTC()
	claims := Claims{
		Email:     user.Email,
		TokenType: tokenType,
		RegisteredClaims: jwt.RegisteredClaims{
			ID:        uuid.NewString(),
			Subject:   user.ID,
			IssuedAt:  jwt.NewNumericDate(now),
			ExpiresAt: jwt.NewNumericDate(now.Add(ttl)),
		},
	}

	return jwt.NewWithClaims(jwt.SigningMethodHS256, claims).SignedString(s.secret)
}

func (s *TokenService) parse(tokenString string, expectedTokenType string) (*Claims, error) {
	claims := &Claims{}
	parser := jwt.NewParser(jwt.WithValidMethods([]string{jwt.SigningMethodHS256.Alg()}))
	token, err := parser.ParseWithClaims(tokenString, claims, func(token *jwt.Token) (interface{}, error) {
		if token.Method == nil || token.Method.Alg() != jwt.SigningMethodHS256.Alg() {
			return nil, ErrInvalidToken
		}

		return s.secret, nil
	})
	if err != nil {
		if errors.Is(err, jwt.ErrTokenExpired) {
			return nil, ErrExpiredToken
		}

		return nil, ErrInvalidToken
	}

	if token == nil || !token.Valid || claims.Subject == "" {
		return nil, ErrInvalidToken
	}

	if claims.TokenType != expectedTokenType {
		return nil, ErrWrongTokenType
	}

	return claims, nil
}
