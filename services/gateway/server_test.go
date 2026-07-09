package main

import (
	"bytes"
	"encoding/json"
	"io"
	"net/http"
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

	redisURL := os.Getenv("REDIS_URL")
	if redisURL == "" {
		redisURL = "redis://127.0.0.1:6379/0"
	}
	redisOpts, err := redis.ParseURL(redisURL)
	if err != nil {
		t.Fatalf("failed to parse redis url: %v", err)
	}
	redisClient := redis.NewClient(redisOpts)

	// Mock User Service!
	mockUserService := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		if r.URL.Path == "/internal/auth/login" || r.URL.Path == "/internal/auth/refresh-tokens" {
			w.WriteHeader(http.StatusOK)
			w.Write([]byte(`{"userId":"00000000-0000-0000-0000-000000000001", "email":"user@example.com", "newTokenId":"mockNewTokenId", "newRawToken":"mockNewRawToken", "expiresAt":"2030-01-01T00:00:00Z"}`))
			return
		}
		w.WriteHeader(http.StatusNotFound)
	}))
	t.Cleanup(mockUserService.Close)

	tokenService := gatewayauth.NewTokenService(testIntegrationJWTSecret, time.Hour, 24*time.Hour)
	httpClient := &http.Client{Timeout: 10 * time.Second}

	authHandler := handlers.NewAuthHandler(redisClient, tokenService, metrics, httpClient, mockUserService.URL, "test-key")

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
	api.Get("/ping", func(c *fiber.Ctx) error {
		return c.SendStatus(fiber.StatusOK)
	})

	return app
}

func login(t *testing.T, app *fiber.App) integrationTokenResponse {
	t.Helper()
	payload := `{"email": "user@example.com", "password": "password"}`
	req := httptest.NewRequest(fiber.MethodPost, "/auth/login", bytes.NewBufferString(payload))
	req.Header.Set(fiber.HeaderContentType, fiber.MIMEApplicationJSON)
	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("login request returned error: %v", err)
	}
	if resp.StatusCode != fiber.StatusOK {
		t.Fatalf("expected login status 200, got %d", resp.StatusCode)
	}

	var data integrationTokenResponse
	if err := json.NewDecoder(resp.Body).Decode(&data); err != nil {
		t.Fatalf("failed to decode login response: %v", err)
	}
	return data
}

func refresh(t *testing.T, app *fiber.App, refreshToken string) integrationTokenResponse {
	t.Helper()
	req := httptest.NewRequest(fiber.MethodPost, "/auth/refresh", nil)
	req.AddCookie(&http.Cookie{Name: "refresh_token", Value: refreshToken})
	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("refresh request returned error: %v", err)
	}
	if resp.StatusCode != fiber.StatusOK {
		t.Fatalf("expected refresh status 200, got %d", resp.StatusCode)
	}

	var data integrationTokenResponse
	if err := json.NewDecoder(resp.Body).Decode(&data); err != nil {
		t.Fatalf("failed to decode refresh response: %v", err)
	}
	return data
}

func useIsolatedPrometheusRegistry(t *testing.T) {
	t.Helper()
	originalRegisterer := prometheus.DefaultRegisterer
	originalGatherer := prometheus.DefaultGatherer
	registry := prometheus.NewRegistry()
	prometheus.DefaultRegisterer = registry
	prometheus.DefaultGatherer = registry
	t.Cleanup(func() {
		prometheus.DefaultRegisterer = originalRegisterer
		prometheus.DefaultGatherer = originalGatherer
	})
}

func hasMetricLine(metricsText, metricName string, expectedLabels []string, expectedValue string) bool {
	lines := strings.Split(metricsText, "\n")
	for _, line := range lines {
		if !strings.HasPrefix(line, metricName) {
			continue
		}
		allLabelsPresent := true
		for _, label := range expectedLabels {
			if !strings.Contains(line, label) {
				allLabelsPresent = false
				break
			}
		}
		if allLabelsPresent && strings.HasSuffix(strings.TrimSpace(line), expectedValue) {
			return true
		}
	}
	return false
}
