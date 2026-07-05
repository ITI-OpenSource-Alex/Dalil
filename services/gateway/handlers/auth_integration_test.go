//go:build integration

package handlers_test

import (
	"bytes"
	"database/sql"
	"encoding/json"
	"net/http/httptest"
	"os"
	"strings"
	"testing"
	"time"

	gatewayauth "github.com/ITI-OpenSource-Alex/GOA/services/gateway/auth"
	"github.com/ITI-OpenSource-Alex/GOA/services/gateway/handlers"
	"github.com/ITI-OpenSource-Alex/GOA/services/gateway/middleware"
	"github.com/ITI-OpenSource-Alex/GOA/services/gateway/observability"
	"github.com/gofiber/fiber/v2"
	_ "github.com/lib/pq"
	"github.com/redis/go-redis/v9"
	"golang.org/x/crypto/bcrypt"
)

func setupIntegrationTestApp(t *testing.T) (*fiber.App, *sql.DB, *redis.Client, *gatewayauth.RefreshTokenRepository, *gatewayauth.TokenService) {
	t.Helper()

	metrics, err := observability.NewMetrics()
	if err != nil {
		t.Fatalf("failed to initialize metrics: %v", err)
	}

	dbURL := os.Getenv("DATABASE_URL")
	if dbURL == "" {
		dbURL = "postgres://goa:goa_pass@localhost:5432/user_db?sslmode=disable"
	}
	db, err := sql.Open("postgres", dbURL)
	if err != nil {
		t.Fatalf("failed to connect to db: %v", err)
	}

	redisURL := os.Getenv("REDIS_URL")
	if redisURL == "" {
		redisURL = "redis://localhost:6379/0"
	}
	redisOpts, err := redis.ParseURL(redisURL)
	if err != nil {
		t.Fatalf("failed to parse redis url: %v", err)
	}
	rdb := redis.NewClient(redisOpts)

	t.Cleanup(func() {
		db.Close()
		rdb.Close()
	})

	tokenService := gatewayauth.NewTokenService("test-integration-secret", time.Hour, 24*time.Hour)
	repo := gatewayauth.NewRefreshTokenRepository(db)
	dbValidator := gatewayauth.NewDatabaseCredentialValidator(db)
	authHandler := handlers.NewAuthHandler(db, rdb, repo, tokenService, dbValidator, metrics)

	app := fiber.New()
	app.Post("/auth/login", authHandler.Login)
	app.Post("/auth/refresh", authHandler.Refresh)
	app.Post("/auth/logout", middleware.JWT("test-integration-secret", rdb, metrics), authHandler.Logout)
	app.Post("/auth/logout-all", middleware.JWT("test-integration-secret", rdb, metrics), authHandler.LogoutAll)

	app.Get("/api/protected", middleware.JWT("test-integration-secret", rdb, metrics), func(c *fiber.Ctx) error {
		return c.SendStatus(fiber.StatusOK)
	})

	return app, db, rdb, repo, tokenService
}

func TestIntegrationAuthFlow(t *testing.T) {
	app, db, _, _, _ := setupIntegrationTestApp(t)

	userID := "00000000-0000-0000-0000-000000000002"
	email := "integration@test.com"
	password := "SecretPass123!"

	// Hash password
	hashedBytes, err := bcrypt.GenerateFromPassword([]byte(password), bcrypt.DefaultCost)
	if err != nil {
		t.Fatalf("failed to hash password: %v", err)
	}
	passwordHash := string(hashedBytes)

	// Clean up and seed
	_, _ = db.Exec("DELETE FROM refresh_tokens WHERE user_id = $1", userID)
	_, _ = db.Exec("DELETE FROM users WHERE id = $1", userID)
	_, err = db.Exec("INSERT INTO users (id, email, \"passwordHash\", is_verified) VALUES ($1, $2, $3, $4)",
		userID, email, passwordHash, true)
	if err != nil {
		t.Fatalf("failed to seed user: %v", err)
	}
	t.Cleanup(func() {
		_, _ = db.Exec("DELETE FROM refresh_tokens WHERE user_id = $1", userID)
		_, _ = db.Exec("DELETE FROM users WHERE id = $1", userID)
	})

	// 1. Test Login
	loginBody, _ := json.Marshal(map[string]string{
		"email":    email,
		"password": password,
	})
	req := httptest.NewRequest(fiber.MethodPost, "/auth/login", bytes.NewReader(loginBody))
	req.Header.Set(fiber.HeaderContentType, fiber.MIMEApplicationJSON)
	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("login request failed: %v", err)
	}
	if resp.StatusCode != fiber.StatusOK {
		t.Fatalf("expected login status 200, got %d", resp.StatusCode)
	}

	// Extract tokens and cookies
	var tokenResp struct {
		AccessToken  string `json:"access_token"`
		RefreshToken string `json:"refresh_token"`
	}
	_ = json.NewDecoder(resp.Body).Decode(&tokenResp)

	var accessTokenCookie, refreshTokenCookie string
	for _, cookie := range resp.Header[fiber.HeaderSetCookie] {
		if strings.HasPrefix(cookie, "access_token=") {
			accessTokenCookie = cookie
		} else if strings.HasPrefix(cookie, "refresh_token=") {
			refreshTokenCookie = cookie
		}
	}

	if tokenResp.AccessToken == "" || tokenResp.RefreshToken == "" {
		t.Fatal("login response missing tokens")
	}
	if accessTokenCookie == "" || refreshTokenCookie == "" {
		t.Fatal("login response missing expected cookies")
	}

	// Extract cookie values
	accessTokenVal := extractCookieValue(accessTokenCookie)
	refreshTokenVal := extractCookieValue(refreshTokenCookie)

	if accessTokenVal == "" || refreshTokenVal == "" {
		t.Fatal("failed to extract cookie values")
	}

	// 2. Test Access Protected Route with valid token
	req = httptest.NewRequest(fiber.MethodGet, "/api/protected", nil)
	req.Header.Set(fiber.HeaderAuthorization, "Bearer "+accessTokenVal)
	resp, _ = app.Test(req)
	if resp.StatusCode != fiber.StatusOK {
		t.Fatalf("expected 200 on protected route, got %d", resp.StatusCode)
	}

	// 3. Test Refresh Token Rotation
	refreshBody, _ := json.Marshal(map[string]string{
		"refresh_token": refreshTokenVal,
	})
	req = httptest.NewRequest(fiber.MethodPost, "/auth/refresh", bytes.NewReader(refreshBody))
	req.Header.Set(fiber.HeaderContentType, fiber.MIMEApplicationJSON)
	req.Header.Set("Cookie", "refresh_token="+refreshTokenVal)
	resp, err = app.Test(req)
	if err != nil {
		t.Fatalf("refresh request failed: %v", err)
	}
	if resp.StatusCode != fiber.StatusOK {
		t.Fatalf("expected refresh status 200, got %d", resp.StatusCode)
	}

	var rotateResp struct {
		AccessToken string `json:"access_token"`
	}
	_ = json.NewDecoder(resp.Body).Decode(&rotateResp)
	if rotateResp.AccessToken == "" || rotateResp.AccessToken == accessTokenVal {
		t.Fatal("expected rotated access token")
	}

	var rotatedRefreshTokenCookie string
	for _, cookie := range resp.Header[fiber.HeaderSetCookie] {
		if strings.HasPrefix(cookie, "refresh_token=") {
			rotatedRefreshTokenCookie = cookie
		}
	}
	if rotatedRefreshTokenCookie == "" {
		t.Fatal("expected new refresh token cookie on rotation")
	}
	rotatedRefreshTokenVal := extractCookieValue(rotatedRefreshTokenCookie)

	// 4. Test Replay Attack Detection
	req = httptest.NewRequest(fiber.MethodPost, "/auth/refresh", bytes.NewReader(refreshBody))
	req.Header.Set(fiber.HeaderContentType, fiber.MIMEApplicationJSON)
	req.Header.Set("Cookie", "refresh_token="+refreshTokenVal)
	resp, _ = app.Test(req)
	if resp.StatusCode != fiber.StatusUnauthorized {
		t.Fatalf("expected replay attack to fail with 401, got %d", resp.StatusCode)
	}

	// Verify that the rotated refresh token is now also revoked in the database
	rotatedParts := strings.Split(rotatedRefreshTokenVal, ".")
	if len(rotatedParts) != 2 {
		t.Fatalf("invalid rotated token format: %s", rotatedRefreshTokenVal)
	}
	var revokedAt interface{}
	err = db.QueryRow("SELECT revoked_at FROM refresh_tokens WHERE id = $1", rotatedParts[0]).Scan(&revokedAt)
	if err != nil {
		t.Fatalf("failed to query rotated token: %v", err)
	}
	if revokedAt == nil {
		t.Fatal("expected rotated token to be revoked after replay attack")
	}

	// 5. Test Logout and Redis Blacklist
	req = httptest.NewRequest(fiber.MethodPost, "/auth/login", bytes.NewReader(loginBody))
	req.Header.Set(fiber.HeaderContentType, fiber.MIMEApplicationJSON)
	resp, _ = app.Test(req)
	_ = json.NewDecoder(resp.Body).Decode(&tokenResp)
	for _, cookie := range resp.Header[fiber.HeaderSetCookie] {
		if strings.HasPrefix(cookie, "access_token=") {
			accessTokenCookie = cookie
		} else if strings.HasPrefix(cookie, "refresh_token=") {
			refreshTokenCookie = cookie
		}
	}
	accessTokenVal = extractCookieValue(accessTokenCookie)
	refreshTokenVal = extractCookieValue(refreshTokenCookie)

	req = httptest.NewRequest(fiber.MethodPost, "/auth/logout", nil)
	req.Header.Set(fiber.HeaderAuthorization, "Bearer "+accessTokenVal)
	req.Header.Set("Cookie", "refresh_token="+refreshTokenVal)
	resp, _ = app.Test(req)
	if resp.StatusCode != fiber.StatusOK {
		t.Fatalf("expected logout status 200, got %d", resp.StatusCode)
	}

	// Verify access token is blacklisted in Redis and returns 401 now
	req = httptest.NewRequest(fiber.MethodGet, "/api/protected", nil)
	req.Header.Set(fiber.HeaderAuthorization, "Bearer "+accessTokenVal)
	resp, _ = app.Test(req)
	if resp.StatusCode != fiber.StatusUnauthorized {
		t.Fatalf("expected 401 for blacklisted token, got %d", resp.StatusCode)
	}
}

func TestLogoutAllIntegration(t *testing.T) {
	app, db, _, _, _ := setupIntegrationTestApp(t)

	userID := "00000000-0000-0000-0000-000000000003"
	email := "logoutall@test.com"
	password := "SecretPass123!"

	hashedBytes, _ := bcrypt.GenerateFromPassword([]byte(password), bcrypt.DefaultCost)
	passwordHash := string(hashedBytes)

	_, _ = db.Exec("DELETE FROM refresh_tokens WHERE user_id = $1", userID)
	_, _ = db.Exec("DELETE FROM users WHERE id = $1", userID)
	_, err := db.Exec("INSERT INTO users (id, email, \"passwordHash\", is_verified) VALUES ($1, $2, $3, $4)",
		userID, email, passwordHash, true)
	if err != nil {
		t.Fatalf("failed to seed user: %v", err)
	}
	t.Cleanup(func() {
		_, _ = db.Exec("DELETE FROM refresh_tokens WHERE user_id = $1", userID)
		_, _ = db.Exec("DELETE FROM users WHERE id = $1", userID)
	})

	loginBody, _ := json.Marshal(map[string]string{
		"email":    email,
		"password": password,
	})

	// Login session 1
	req := httptest.NewRequest(fiber.MethodPost, "/auth/login", bytes.NewReader(loginBody))
	req.Header.Set(fiber.HeaderContentType, fiber.MIMEApplicationJSON)
	resp, _ := app.Test(req)
	var tokens1 struct {
		AccessToken  string `json:"access_token"`
		RefreshToken string `json:"refresh_token"`
	}
	_ = json.NewDecoder(resp.Body).Decode(&tokens1)

	// Login session 2
	req = httptest.NewRequest(fiber.MethodPost, "/auth/login", bytes.NewReader(loginBody))
	req.Header.Set(fiber.HeaderContentType, fiber.MIMEApplicationJSON)
	resp, _ = app.Test(req)
	var tokens2 struct {
		AccessToken  string `json:"access_token"`
		RefreshToken string `json:"refresh_token"`
	}
	_ = json.NewDecoder(resp.Body).Decode(&tokens2)

	// Call logout-all using session 1 access token
	req = httptest.NewRequest(fiber.MethodPost, "/auth/logout-all", nil)
	req.Header.Set(fiber.HeaderAuthorization, "Bearer "+tokens1.AccessToken)
	resp, _ = app.Test(req)
	if resp.StatusCode != fiber.StatusOK {
		t.Fatalf("expected logout-all status 200, got %d", resp.StatusCode)
	}

	// Verify session 1 access token is blacklisted
	req = httptest.NewRequest(fiber.MethodGet, "/api/protected", nil)
	req.Header.Set(fiber.HeaderAuthorization, "Bearer "+tokens1.AccessToken)
	resp, _ = app.Test(req)
	if resp.StatusCode != fiber.StatusUnauthorized {
		t.Fatalf("expected session 1 access token to be unauthorized, got %d", resp.StatusCode)
	}

	// Verify all refresh tokens for user are revoked in the DB
	var activeCount int
	err = db.QueryRow("SELECT COUNT(*) FROM refresh_tokens WHERE user_id = $1 AND revoked_at IS NULL", userID).Scan(&activeCount)
	if err != nil {
		t.Fatalf("failed to query refresh tokens: %v", err)
	}
	if activeCount != 0 {
		t.Fatalf("expected 0 active refresh tokens, got %d", activeCount)
	}
}

func extractCookieValue(cookieHeader string) string {
	parts := strings.Split(cookieHeader, ";")
	if len(parts) == 0 {
		return ""
	}
	cookieParts := strings.SplitN(parts[0], "=", 2)
	if len(cookieParts) != 2 {
		return ""
	}
	return cookieParts[1]
}
