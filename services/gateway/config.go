package main

import (
	"bufio"
	"errors"
	"fmt"
	"os"
	"strings"
	"time"

	"github.com/kelseyhightower/envconfig"
)

type Config struct {
	Port                   string        `envconfig:"PORT" default:"8080"`
	JWTSecret              string        `envconfig:"JWT_SECRET" required:"true"`
	RedisURL               string        `envconfig:"REDIS_URL" required:"true"`
	Version                string        `envconfig:"VERSION" default:"0.1.0"`
	AccessTokenTTL         time.Duration `envconfig:"ACCESS_TOKEN_TTL" default:"1h"`
	RefreshTokenTTL        time.Duration `envconfig:"REFRESH_TOKEN_TTL" default:"720h"`
	ReadTimeout            time.Duration `envconfig:"READ_TIMEOUT" default:"5s"`
	WriteTimeout           time.Duration `envconfig:"WRITE_TIMEOUT" default:"10s"`
	ShutdownTimeout        time.Duration `envconfig:"SHUTDOWN_TIMEOUT" default:"10s"`
	SecureCookies          bool          `envconfig:"SECURE_COOKIES" default:"false"`
	WritingServiceURL      string        `envconfig:"WRITING_SERVICE_URL" required:"true"`
	ExamServiceURL         string        `envconfig:"EXAM_SERVICE_URL" required:"true"`
	NotificationServiceURL string        `envconfig:"NOTIFICATION_SERVICE_URL" default:"http://notification:8087"`
	// Chat is proxied rather than called from the browser, so the Gateway needs
	// to know where Orchestration lives (BUG-029, BUG-044).
	OrchestrationServiceURL string        `envconfig:"ORCHESTRATION_SERVICE_URL" default:"http://orchestration:8083"`
	// GOA-132: the Gateway now proxies Speaking's session routes and its
	// WebSocket, and exposes RAG's profile matching. SpeakingServiceURL is the
	// http:// address; the ws:// upstream is derived from it in
	// handlers.NewSpeakingWSHandler so the two cannot drift to different hosts.
	// The WebSocket proxy also picks up JWT auth, the paid-tier gate and exam
	// session ownership, none of which the browser's direct connection to
	// :8082 ever had (GOA-059).
	SpeakingServiceURL      string        `envconfig:"SPEAKING_SERVICE_URL" default:"http://speaking:8082"`
	RAGServiceURL           string        `envconfig:"RAG_SERVICE_URL" default:"http://rag:8084"`
	UserServiceURL          string        `envconfig:"USER_SERVICE_URL" required:"true"`
	InternalApiKey          string        `envconfig:"INTERNAL_API_KEY" required:"true"`
	AdminAPIKey             string        `envconfig:"ADMIN_API_KEY"`
	AWSRegion               string        `envconfig:"AWS_REGION" default:"us-east-1"`
	AWSEndpointURL          string        `envconfig:"AWS_ENDPOINT_URL"`
	IngestionQueueURL       string        `envconfig:"INGESTION_QUEUE_URL"`
	SubscriptionUpgradeURL  string        `envconfig:"SUBSCRIPTION_UPGRADE_URL" default:"/upgrade"`
	SubscriptionCacheTTL    time.Duration `envconfig:"SUBSCRIPTION_CACHE_TTL" default:"5m"`
	// Exam sessions a single candidate may open per hour. Sitting a full exam
	// takes far longer than 20 minutes, so a legitimate candidate never reaches
	// three; the ceiling exists to stop a loop from draining the question bank's
	// unseen-question pool and burning grading spend (GOA-059).
	ExamStartLimitPerHour int           `envconfig:"EXAM_START_LIMIT_PER_HOUR" default:"3"`
	ExamOwnershipCacheTTL time.Duration `envconfig:"EXAM_OWNERSHIP_CACHE_TTL" default:"5m"`
	// Comma-separated origin allow-list for CORS. Cannot be "*" because auth
	// rides on HttpOnly cookies and the spec forbids wildcard + credentials.
	CORSAllowedOrigins  string  `envconfig:"CORS_ALLOWED_ORIGINS" default:"http://localhost:3000"`

	// GOA-034: per-endpoint AI quotas (OWASP LLM04). Zero disables a limit,
	// which is how the E2E suite and the load test run without weakening the
	// shipped defaults.
	ChatQueriesPerHour   int `envconfig:"CHAT_QUERIES_PER_HOUR" default:"20"`
	// GOA-132: /match runs a scoring pass per program row, each with a potential
	// LLM boost, so opportunity search is a real spend path rather than a cheap
	// read and gets the same treatment as chat and essay evaluation.
	OpportunitySearchesPerHour int `envconfig:"OPPORTUNITY_SEARCHES_PER_HOUR" default:"20"`
	EssayEvalsPerHour    int `envconfig:"ESSAY_EVALS_PER_HOUR" default:"5"`
	CVReviewsPerHour     int `envconfig:"CV_REVIEWS_PER_HOUR" default:"5"`
	BudgetUSD           float64 `envconfig:"BUDGET_USD" default:"150.0"`
	CostPromptPer1M     float64 `envconfig:"COST_PROMPT_PER_1M" default:"2.0"`
	CostCompletionPer1M float64 `envconfig:"COST_COMPLETION_PER_1M" default:"10.0"`
	LLMPricingJSON      string  `envconfig:"LLM_PRICING_JSON" default:"{\"claude-opus-4-8\":{\"prompt_per_1m\":2,\"completion_per_1m\":10},\"glm-5.2\":{\"prompt_per_1m\":6,\"completion_per_1m\":9},\"gpt-5.5\":{\"prompt_per_1m\":7,\"completion_per_1m\":14},\"claude-opus-4-6\":{\"prompt_per_1m\":8,\"completion_per_1m\":40},\"claude-opus-4-7\":{\"prompt_per_1m\":8,\"completion_per_1m\":40}}"`
}

func LoadConfig() (Config, error) {
	if err := loadDotEnv(".env"); err != nil {
		return Config{}, err
	}

	var cfg Config
	if err := envconfig.Process("", &cfg); err != nil {
		return Config{}, err
	}

	return cfg, nil
}

func loadDotEnv(path string) error {
	file, err := os.Open(path)
	if err != nil {
		if errors.Is(err, os.ErrNotExist) {
			return nil
		}

		return err
	}
	defer file.Close()

	scanner := bufio.NewScanner(file)
	lineNumber := 0
	for scanner.Scan() {
		lineNumber++
		line := strings.TrimSpace(scanner.Text())
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}

		line = strings.TrimPrefix(line, "export ")
		key, value, ok := strings.Cut(line, "=")
		if !ok {
			return fmt.Errorf("invalid .env line %d", lineNumber)
		}

		key = strings.TrimSpace(key)
		value = strings.Trim(strings.TrimSpace(value), `"'`)
		if key == "" {
			return fmt.Errorf("invalid .env key on line %d", lineNumber)
		}

		if _, exists := os.LookupEnv(key); !exists {
			if err := os.Setenv(key, value); err != nil {
				return err
			}
		}
	}

	return scanner.Err()
}
