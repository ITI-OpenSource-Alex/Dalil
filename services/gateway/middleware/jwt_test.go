package middleware

import (
	"crypto/rand"
	"crypto/rsa"
	"net/http/httptest"
	"testing"
	"time"

	gatewayauth "github.com/ITI-OpenSource-Alex/GOA/services/gateway/auth"
	"github.com/gofiber/fiber/v2"
	"github.com/golang-jwt/jwt/v5"
)

const testJWTSecret = "test-secret"

func TestJWTRejectsInvalidTokens(t *testing.T) {
	tests := []struct {
		name          string
		authorization string
	}{
		{
			name:          "missing token",
			authorization: "",
		},
		{
			name:          "malformed bearer header",
			authorization: "Bearer",
		},
		{
			name:          "invalid signature",
			authorization: "Bearer " + signTestAccessToken(t, "wrong-secret", time.Hour, jwt.SigningMethodHS256),
		},
		{
			name:          "expired token",
			authorization: "Bearer " + signTestAccessToken(t, testJWTSecret, -time.Hour, jwt.SigningMethodHS256),
		},
		{
			name:          "wrong signing method",
			authorization: "Bearer " + signTestAccessToken(t, testJWTSecret, time.Hour, jwt.SigningMethodHS512),
		},
		{
			name:          "unsigned token",
			authorization: "Bearer " + signUnsignedTestAccessToken(t),
		},
		{
			name:          "rsa signing method",
			authorization: "Bearer " + signRSATestAccessToken(t),
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			app := newJWTTestApp()
			req := httptest.NewRequest(fiber.MethodGet, "/protected", nil)
			if tt.authorization != "" {
				req.Header.Set(fiber.HeaderAuthorization, tt.authorization)
			}

			resp, err := app.Test(req)
			if err != nil {
				t.Fatalf("app.Test returned error: %v", err)
			}
			if resp.StatusCode != fiber.StatusUnauthorized {
				t.Fatalf("expected status 401, got %d", resp.StatusCode)
			}
		})
	}
}

func TestJWTAcceptsValidHS256TokenAndStoresUserID(t *testing.T) {
	app := newJWTTestApp()
	req := httptest.NewRequest(fiber.MethodGet, "/protected", nil)
	req.Header.Set(fiber.HeaderAuthorization, "Bearer "+signTestAccessToken(t, testJWTSecret, time.Hour, jwt.SigningMethodHS256))

	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("app.Test returned error: %v", err)
	}
	if resp.StatusCode != fiber.StatusOK {
		t.Fatalf("expected status 200, got %d", resp.StatusCode)
	}
}

func newJWTTestApp() *fiber.App {
	app := fiber.New()
	app.Use(JWT(testJWTSecret))
	app.Get("/protected", func(c *fiber.Ctx) error {
		userID, _ := c.Locals(ContextKeyUserID).(string)
		if userID != "user-1" {
			return fiber.NewError(fiber.StatusInternalServerError, "user_id not stored")
		}

		return c.SendStatus(fiber.StatusOK)
	})

	return app
}

func signTestAccessToken(t *testing.T, secret string, ttl time.Duration, method jwt.SigningMethod) string {
	t.Helper()

	now := time.Now().UTC()
	claims := gatewayauth.Claims{
		Email:     "user@example.com",
		TokenType: gatewayauth.AccessTokenType,
		RegisteredClaims: jwt.RegisteredClaims{
			Subject:   "user-1",
			IssuedAt:  jwt.NewNumericDate(now),
			ExpiresAt: jwt.NewNumericDate(now.Add(ttl)),
		},
	}

	token, err := jwt.NewWithClaims(method, claims).SignedString([]byte(secret))
	if err != nil {
		t.Fatalf("failed to sign token: %v", err)
	}

	return token
}

func signUnsignedTestAccessToken(t *testing.T) string {
	t.Helper()

	now := time.Now().UTC()
	claims := gatewayauth.Claims{
		Email:     "user@example.com",
		TokenType: gatewayauth.AccessTokenType,
		RegisteredClaims: jwt.RegisteredClaims{
			Subject:   "user-1",
			IssuedAt:  jwt.NewNumericDate(now),
			ExpiresAt: jwt.NewNumericDate(now.Add(time.Hour)),
		},
	}

	token, err := jwt.NewWithClaims(jwt.SigningMethodNone, claims).SignedString(jwt.UnsafeAllowNoneSignatureType)
	if err != nil {
		t.Fatalf("failed to sign unsigned token: %v", err)
	}

	return token
}

func signRSATestAccessToken(t *testing.T) string {
	t.Helper()

	privateKey, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		t.Fatalf("failed to generate RSA key: %v", err)
	}

	now := time.Now().UTC()
	claims := gatewayauth.Claims{
		Email:     "user@example.com",
		TokenType: gatewayauth.AccessTokenType,
		RegisteredClaims: jwt.RegisteredClaims{
			Subject:   "user-1",
			IssuedAt:  jwt.NewNumericDate(now),
			ExpiresAt: jwt.NewNumericDate(now.Add(time.Hour)),
		},
	}

	token, err := jwt.NewWithClaims(jwt.SigningMethodRS256, claims).SignedString(privateKey)
	if err != nil {
		t.Fatalf("failed to sign RSA token: %v", err)
	}

	return token
}
