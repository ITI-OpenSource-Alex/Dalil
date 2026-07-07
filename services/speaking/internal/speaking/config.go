package speaking

import (
	"os"
	"strconv"
)

type Config struct {
	Port              string
	MaxConnections    int
	ElevenLabsAPIKey  string
	OtelServiceName   string
	LangfusePublicKey string
	LangfuseSecretKey string
	LangfuseHost      string
	DatabaseURL       string
}

func LoadConfig() *Config {
	port := getEnv("PORT", "8082")
	maxConnStr := getEnv("MAX_CONNECTIONS", "100")
	maxConn, err := strconv.Atoi(maxConnStr)
	if err != nil {
		maxConn = 100
	}

	return &Config{
		Port:              port,
		MaxConnections:    maxConn,
		ElevenLabsAPIKey:  getEnv("ELEVENLABS_API_KEY", ""),
		OtelServiceName:   getEnv("OTEL_SERVICE_NAME", "speaking"),
		LangfusePublicKey: getEnv("LANGFUSE_PUBLIC_KEY", ""),
		LangfuseSecretKey: getEnv("LANGFUSE_SECRET_KEY", ""),
		LangfuseHost:      getEnv("LANGFUSE_HOST", "https://cloud.langfuse.com"),
		DatabaseURL:       getEnv("DATABASE_URL", "postgresql://goa:goa_pass@postgres:5432/speaking_db"),
	}
}

func getEnv(key, defaultVal string) string {
	if value, exists := os.LookupEnv(key); exists {
		return value
	}
	return defaultVal
}
