package main

import (
	"context"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/prometheus/client_golang/prometheus/promhttp"
	"github.com/rs/zerolog"
	"github.com/rs/zerolog/log"

	"github.com/ITI-OpenSource-Alex/GOA/services/speaking/db"
	"github.com/ITI-OpenSource-Alex/GOA/services/speaking/internal/speaking"
	"github.com/ITI-OpenSource-Alex/GOA/services/speaking/langfuse"
	"github.com/ITI-OpenSource-Alex/GOA/services/speaking/llm"
	"github.com/ITI-OpenSource-Alex/GOA/services/speaking/tts"
)

func main() {
	zerolog.TimeFieldFormat = zerolog.TimeFormatUnix
	log.Logger = log.Output(os.Stdout)

	cfg := speaking.LoadConfig()
	log.Info().Str("port", cfg.Port).Int("max_connections", cfg.MaxConnections).Msg("Starting Speaking Service")

	// 1. Initialize PostgreSQL Connection Pool
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	dbPool, err := pgxpool.New(ctx, cfg.DatabaseURL)
	if err != nil {
		log.Fatal().Err(err).Msg("Unable to connect to database connection pool")
	}
	defer dbPool.Close()

	// Ping database to verify connection is active
	err = dbPool.Ping(ctx)
	if err != nil {
		log.Fatal().Err(err).Msg("Database ping failed")
	}
	log.Info().Msg("Successfully established PostgreSQL connection pool")

	// 2. Initialize Repositories and Specialist Clients
	dbRepo := db.NewPostgresRepository(dbPool)

	// Fetch API keys from environment or config settings
	anthropicAPIKey := os.Getenv("ANTHROPIC_API_KEY")
	llmClient := llm.NewClient(anthropicAPIKey)
	ttsClient := tts.NewClient(cfg.ElevenLabsAPIKey)
	langfuseClient := langfuse.NewClient(cfg.LangfusePublicKey, cfg.LangfuseSecretKey, cfg.LangfuseHost)

	speaking.StartBackgroundTasks()

	// 3. HTTP Server configuration
	http.HandleFunc("/ws", func(w http.ResponseWriter, r *http.Request) {
		speaking.HandleWebSocket(w, r, cfg, dbRepo, llmClient, ttsClient, langfuseClient)
	})

	http.Handle("/metrics", promhttp.Handler())

	server := &http.Server{
		Addr:    ":" + cfg.Port,
		Handler: nil,
	}

	// 4. Graceful Shutdown & Drain handling
	go func() {
		if err := server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Fatal().Err(err).Msg("Server HTTP listen failed")
		}
	}()

	// Intercept SIGTERM/SIGINT signals
	stop := make(chan os.Signal, 1)
	signal.Notify(stop, syscall.SIGINT, syscall.SIGTERM)
	<-stop

	log.Info().Msg("Shutting down Speaking Service gracefully...")

	// Create shutdown deadline (5 seconds maximum drain window)
	shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer shutdownCancel()

	if err := server.Shutdown(shutdownCtx); err != nil {
		log.Error().Err(err).Msg("HTTP server shutdown error")
	}

	log.Info().Msg("Speaking Service shutdown complete")
}
