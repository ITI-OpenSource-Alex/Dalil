package main

import (
	"context"
	"database/sql"
	"encoding/json"
	"io"
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
	"github.com/prometheus/client_golang/prometheus"
	"github.com/redis/go-redis/v9"
	"github.com/rs/zerolog"
)

func TestAuthAndProtectedRoutesIntegration(t *testing.T) {
	app := newIntegrationTestApp(t)
	tokenService := gatewayauth.NewTokenService(testIntegrationJWTSecret, time.Hour, 24*time.Hour)

	loginTokens := login(t, app)
	accessClaims, err := tokenService.ParseAccessToken(loginTokens.AccessToken)
	if err != nil {
		t.Fatalf("login access token was not valid: %v", err)
	}
	if accessClaims.Subject != "00000000-0000-0000-0000-000000000001" {
		t.Fatalf("expected subject 00000000-0000-0000-0000-000000000001, got %q", accessClaims.Subject)
	}

	refreshedTokens := refresh(t, app, loginTokens.RefreshToken)
	if refreshedTokens.AccessToken == "" {
		t.Fatal("expected refresh response to include an access token")
	}
	if refreshedTokens.AccessToken == loginTokens.AccessToken {
		t.Fatal("expected refresh to return a newly signed access token")
	}
	if _, err := tokenService.ParseAccessToken(refreshedTokens.AccessToken); err != nil {
		t.Fatalf("refreshed access token was not valid: %v", err)
	}

	noTokenResp, err := app.Test(httptest.NewRequest(fiber.MethodGet, "/api/ping", nil))
	if err != nil {
		t.Fatalf("protected route without token returned error: %v", err)
	}
	if noTokenResp.StatusCode != fiber.StatusUnauthorized {
		t.Fatalf("expected protected route without token to return 401, got %d", noTokenResp.StatusCode)
	}

	req := httptest.NewRequest(fiber.MethodGet, "/api/ping", nil)
	req.Header.Set(fiber.HeaderAuthorization, "Bearer "+loginTokens.AccessToken)
	validTokenResp, err := app.Test(req)
	if err != nil {
		t.Fatalf("protected route with token returned error: %v", err)
	}
	if validTokenResp.StatusCode != fiber.StatusOK {
		t.Fatalf("expected protected route with token to return 200, got %d", validTokenResp.StatusCode)
	}
}

func TestMetricsEndpointIncludesThreeRecordedRequests(t *testing.T) {
	app := newIntegrationTestApp(t)

	for i := 0; i < 3; i++ {
		resp, err := app.Test(httptest.NewRequest(fiber.MethodGet, "/health", nil))
		if err != nil {
			t.Fatalf("health request %d returned error: %v", i+1, err)
		}
		if resp.StatusCode != fiber.StatusOK {
			t.Fatalf("health request %d expected status 200, got %d", i+1, resp.StatusCode)
		}
	}

	resp, err := app.Test(httptest.NewRequest(fiber.MethodGet, "/metrics", nil))
	if err != nil {
		t.Fatalf("metrics request returned error: %v", err)
	}
	if resp.StatusCode != fiber.StatusOK {
		t.Fatalf("expected metrics status 200, got %d", resp.StatusCode)
	}

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		t.Fatalf("failed to read metrics body: %v", err)
	}
	metricsText := string(body)
	if !hasMetricLine(
		metricsText,
		"goa_gateway_requests_total",
		[]string{`route="/health"`, `method="GET"`, `status_code="200"`},
		"3",
	) {
		t.Fatalf("expected metrics to include three successful health requests, got:\n%s", metricsText)
	}
}

const testIntegrationJWTSecret = "integration-secret"

type integrationTokenResponse struct {
	AccessToken  string `json:"access_token"`
	RefreshToken string `json:"refresh_token"`
}

func newIntegrationTestApp(t *testing.T) *fiber.App {
	t.Helper()
	useIsolatedPrometheusRegistry(t)

	metrics, err := observability.NewMetrics()
	if err != nil {
		t.Fatalf("NewMetrics returned error: %v", err)
	}

	logger := zerolog.Nop()

	dbURL := os.Getenv("DATABASE_URL")
	if dbURL == "" {
		dbURL = "postgres://goa:goa_pass@localhost:5432/user_db?sslmode=disable"
	}
	db, err := sql.Open("postgres", dbURL)
	if err != nil {
		t.Fatalf("failed to open database: %v", err)
	}
	t.Cleanup(func() { db.Close() })

	redisURL := os.Getenv("REDIS_URL")
	if redisURL == "" {
		redisURL = "redis://localhost:6379/0"
	}
	redisOpts, err := redis.ParseURL(redisURL)
	if err != nil {
		t.Fatalf("failed to parse redis url: %v", err)
	}
	redisClient := redis.NewClient(redisOpts)
	t.Cleanup(func() { redisClient.Close() })

	// Seed test user so foreign keys don't fail
	_, _ = db.Exec("DELETE FROM refresh_tokens WHERE user_id = $1", "00000000-0000-0000-0000-000000000001")
	_, _ = db.Exec("DELETE FROM users WHERE id = $1", "00000000-0000-0000-0000-000000000001")
	_, err = db.Exec("INSERT INTO users (id, email, \"passwordHash\", is_verified) VALUES ($1, $2, $3, $4)",
		"00000000-0000-0000-0000-000000000001", "user@example.com", "dummy_hash", true)
	if err != nil {
		t.Fatalf("failed to seed test user: %v", err)
	}

	tokenService := gatewayauth.NewTokenService(testIntegrationJWTSecret, time.Hour, 24*time.Hour)
	repo := gatewayauth.NewRefreshTokenRepository(db)
	authHandler := handlers.NewAuthHandler(db, redisClient, repo, tokenService, gatewayauth.StaticCredentialValidator{}, metrics)

	app := fiber.New(fiber.Config{
		ErrorHandler: middleware.ErrorHandler(logger),
	})
	app.Use(middleware.RequestID())
	app.Use(middleware.RequestLogger(logger, metrics))
	app.Get("/health", handlers.Health(time.Now(), "0.1.0"))
	app.Get("/metrics", handlers.Metrics())
	app.Post("/auth/login", authHandler.Login)
	app.Post("/auth/refresh", authHandler.Refresh)

	api := app.Group("/api", middleware.JWT(testIntegrationJWTSecret, redisClient, metrics))
	api.Use(middleware.RateLimiter(newIntegrationRateLimitStore(), 60, metrics))
	api.Get("/ping", func(c *fiber.Ctx) error {
		return c.JSON(fiber.Map{"status": "ok"})
	})

	return app
}

func useIsolatedPrometheusRegistry(t *testing.T) {
	t.Helper()

	oldRegisterer := prometheus.DefaultRegisterer
	oldGatherer := prometheus.DefaultGatherer
	registry := prometheus.NewRegistry()
	prometheus.DefaultRegisterer = registry
	prometheus.DefaultGatherer = registry
	t.Cleanup(func() {
		prometheus.DefaultRegisterer = oldRegisterer
		prometheus.DefaultGatherer = oldGatherer
	})
}

func login(t *testing.T, app *fiber.App) integrationTokenResponse {
	t.Helper()

	req := httptest.NewRequest(
		fiber.MethodPost,
		"/auth/login",
		strings.NewReader(`{"email":"user@example.com","password":"password"}`),
	)
	req.Header.Set(fiber.HeaderContentType, fiber.MIMEApplicationJSON)

	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("login request returned error: %v", err)
	}
	if resp.StatusCode != fiber.StatusOK {
		t.Fatalf("expected login status 200, got %d", resp.StatusCode)
	}

	return decodeTokenResponse(t, resp.Body)
}

func refresh(t *testing.T, app *fiber.App, refreshToken string) integrationTokenResponse {
	t.Helper()

	req := httptest.NewRequest(
		fiber.MethodPost,
		"/auth/refresh",
		strings.NewReader(`{"refresh_token":"`+refreshToken+`"}`),
	)
	req.Header.Set(fiber.HeaderContentType, fiber.MIMEApplicationJSON)

	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("refresh request returned error: %v", err)
	}
	if resp.StatusCode != fiber.StatusOK {
		t.Fatalf("expected refresh status 200, got %d", resp.StatusCode)
	}

	return decodeTokenResponse(t, resp.Body)
}

func decodeTokenResponse(t *testing.T, body io.Reader) integrationTokenResponse {
	t.Helper()

	var tokens integrationTokenResponse
	if err := json.NewDecoder(body).Decode(&tokens); err != nil {
		t.Fatalf("failed to decode token response: %v", err)
	}

	return tokens
}

func hasMetricLine(metricsText string, metricName string, labels []string, value string) bool {
	for _, line := range strings.Split(metricsText, "\n") {
		if !strings.HasPrefix(line, metricName+"{") {
			continue
		}
		if !strings.HasSuffix(line, " "+value) {
			continue
		}

		matchesLabels := true
		for _, label := range labels {
			if !strings.Contains(line, label) {
				matchesLabels = false
				break
			}
		}
		if matchesLabels {
			return true
		}
	}

	return false
}

type integrationRateLimitStore struct {
	counts map[string]int64
	ttls   map[string]time.Duration
}

func newIntegrationRateLimitStore() *integrationRateLimitStore {
	return &integrationRateLimitStore{
		counts: make(map[string]int64),
		ttls:   make(map[string]time.Duration),
	}
}

func (s *integrationRateLimitStore) Incr(_ context.Context, key string) *redis.IntCmd {
	s.counts[key]++
	return redis.NewIntResult(s.counts[key], nil)
}

func (s *integrationRateLimitStore) Expire(_ context.Context, key string, expiration time.Duration) *redis.BoolCmd {
	s.ttls[key] = expiration
	return redis.NewBoolResult(true, nil)
}

func (s *integrationRateLimitStore) TTL(_ context.Context, key string) *redis.DurationCmd {
	ttl := s.ttls[key]
	if ttl == 0 {
		ttl = time.Minute
	}

	return redis.NewDurationResult(ttl, nil)
}
