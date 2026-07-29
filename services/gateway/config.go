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
	Port              string        `envconfig:"PORT" default:"8080"`
	JWTSecret         string        `envconfig:"JWT_SECRET" required:"true"`
	RedisURL          string        `envconfig:"REDIS_URL" required:"true"`
	Version           string        `envconfig:"VERSION" default:"0.1.0"`
	AccessTokenTTL    time.Duration `envconfig:"ACCESS_TOKEN_TTL" default:"1h"`
	RefreshTokenTTL   time.Duration `envconfig:"REFRESH_TOKEN_TTL" default:"720h"`
	ReadTimeout       time.Duration `envconfig:"READ_TIMEOUT" default:"5s"`
	WriteTimeout      time.Duration `envconfig:"WRITE_TIMEOUT" default:"10s"`
	ShutdownTimeout   time.Duration `envconfig:"SHUTDOWN_TIMEOUT" default:"10s"`
	SecureCookies     bool          `envconfig:"SECURE_COOKIES" default:"false"`
	WritingServiceURL      string `envconfig:"WRITING_SERVICE_URL" required:"true"`
	ExamServiceURL         string `envconfig:"EXAM_SERVICE_URL" required:"true"`
	NotificationServiceURL string `envconfig:"NOTIFICATION_SERVICE_URL" default:"http://notification:8087"`
	// Chat is proxied rather than called from the browser, so the Gateway needs
	// to know where Orchestration lives (BUG-029, BUG-044).
	OrchestrationServiceURL string `envconfig:"ORCHESTRATION_SERVICE_URL" default:"http://orchestration:8083"`
	UserServiceURL          string `envconfig:"USER_SERVICE_URL" required:"true"`
	InternalApiKey          string `envconfig:"INTERNAL_API_KEY" required:"true"`
	// Comma-separated origin allow-list for CORS. Cannot be "*" because auth
	// rides on HttpOnly cookies and the spec forbids wildcard + credentials.
	CORSAllowedOrigins  string  `envconfig:"CORS_ALLOWED_ORIGINS" default:"http://localhost:3000"`
	BudgetUSD           float64 `envconfig:"BUDGET_USD" default:"150.0"`
	CostPromptPer1M     float64 `envconfig:"COST_PROMPT_PER_1M" default:"2.0"`
	CostCompletionPer1M float64 `envconfig:"COST_COMPLETION_PER_1M" default:"10.0"`
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
