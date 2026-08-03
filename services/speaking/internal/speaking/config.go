package speaking

import (
	"os"
	"strconv"
)

type Config struct {
	Port                         string
	MaxConnections               int
	ElevenLabsAPIKey             string
	OtelServiceName              string
	LangfusePublicKey            string
	LangfuseSecretKey            string
	LangfuseHost                 string
	DatabaseURL                  string
	SpeechServiceURL             string
	AWSRegion                    string
	AWSEndpointURL               string
	AccountDeletedQueueName      string
	RetentionCleanupIntervalHour int
}

func LoadConfig() *Config {
	port := getEnv("PORT", "8082")
	maxConnStr := getEnv("MAX_CONNECTIONS", "100")
	maxConn, err := strconv.Atoi(maxConnStr)
	if err != nil {
		maxConn = 100
	}

	return &Config{
		Port:                         port,
		MaxConnections:               maxConn,
		ElevenLabsAPIKey:             getEnv("ELEVENLABS_API_KEY", ""),
		OtelServiceName:              getEnv("OTEL_SERVICE_NAME", "speaking"),
		LangfusePublicKey:            getEnv("LANGFUSE_PUBLIC_KEY", ""),
		LangfuseSecretKey:            getEnv("LANGFUSE_SECRET_KEY", ""),
		LangfuseHost:                 getEnv("LANGFUSE_HOST", "https://cloud.langfuse.com"),
		DatabaseURL:                  getEnv("DATABASE_URL", "postgresql://goa:goa_pass@postgres:5432/speaking_db"),
		SpeechServiceURL:             getEnv("SPEECH_SERVICE_URL", "http://speech:8086"),
		AWSRegion:                    getEnv("AWS_REGION", "us-east-1"),
		AWSEndpointURL:               getEnv("AWS_ENDPOINT_URL", ""),
		AccountDeletedQueueName:      getEnv("SQS_QUEUE_NAME", "user-events-speaking"),
		RetentionCleanupIntervalHour: getEnvInt("SPEAKING_RETENTION_CLEANUP_INTERVAL_HOURS", 24*7),
	}
}

func getEnv(key, defaultVal string) string {
	if value, exists := os.LookupEnv(key); exists {
		return value
	}
	return defaultVal
}

func getEnvInt(key string, defaultVal int) int {
	value, exists := os.LookupEnv(key)
	if !exists {
		return defaultVal
	}
	parsed, err := strconv.Atoi(value)
	if err != nil {
		return defaultVal
	}
	return parsed
}
