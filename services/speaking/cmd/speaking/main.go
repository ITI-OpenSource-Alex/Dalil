package main

import (
	"context"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/rs/zerolog"
	"github.com/rs/zerolog/log"

	"github.com/ITI-OpenSource-Alex/GOA/services/speaking/db"
	"github.com/ITI-OpenSource-Alex/GOA/services/speaking/internal/speaking"
	"github.com/ITI-OpenSource-Alex/GOA/services/speaking/langfuse"
	"github.com/ITI-OpenSource-Alex/GOA/services/speaking/llm"
	"github.com/ITI-OpenSource-Alex/GOA/services/speaking/migrations"
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

	// Apply migrations before anything can try to write. Fatal on failure: a
	// speaking service that cannot persist is worse than one that will not start,
	// because it answers every session successfully and silently discards the
	// result — which is precisely what happened while nothing ran these at all
	// (BUG-039).
	if err := db.RunMigrations(ctx, dbPool, migrations.FS); err != nil {
		log.Fatal().Err(err).Msg("Database migrations failed")
	}

	// 2. Initialize Repositories and Specialist Clients
	dbRepo := db.NewPostgresRepository(dbPool)

	// Fetch API keys and config from environment
	anthropicAPIKey := os.Getenv("ANTHROPIC_AUTH_TOKEN")
	if anthropicAPIKey == "" {
		anthropicAPIKey = os.Getenv("ANTHROPIC_API_KEY")
	}
	baseURL := os.Getenv("ANTHROPIC_BASE_URL")

	practiceModel := os.Getenv("SPEAKING_PRACTICE_MODEL")
	if practiceModel == "" {
		practiceModel = "claude-opus-4-8"
	}
	examModel := os.Getenv("SPEAKING_EXAM_MODEL")
	if examModel == "" {
		examModel = "claude-opus-4-8"
	}

	// Log the EFFECTIVE provider, not the intended one.
	//
	// docker compose gives shell environment variables precedence over .env, so
	// a stray `ANTHROPIC_BASE_URL` exported in the operator's shell silently
	// overrides the project's configuration. That happened: an AgentRouter key
	// was posted to api.anthropic.com and every agent came back 401, with
	// nothing anywhere in the logs naming the host actually being called.
	// One line here turns a half-hour of bisecting into a glance.
	effectiveBaseURL := baseURL
	if effectiveBaseURL == "" {
		effectiveBaseURL = "https://api.anthropic.com (SDK default)"
	}
	log.Info().
		Str("llm_base_url", effectiveBaseURL).
		Str("practice_model", practiceModel).
		Str("exam_model", examModel).
		Bool("credential_present", anthropicAPIKey != "").
		Str("speech_service_url", cfg.SpeechServiceURL).
		Msg("Speaking upstreams resolved")

	practiceLLMClient := llm.NewClient(practiceModel, anthropicAPIKey, baseURL)
	examLLMClient := llm.NewClient(examModel, anthropicAPIKey, baseURL)
	ttsClient := tts.NewClient(cfg.SpeechServiceURL)
	langfuseClient := langfuse.NewClient(cfg.LangfusePublicKey, cfg.LangfuseSecretKey, cfg.LangfuseHost)

	speaking.StartBackgroundTasks()
	appCtx, appCancel := context.WithCancel(context.Background())
	defer appCancel()
	speaking.StartAccountDeletedConsumer(appCtx, cfg, dbRepo)
	speaking.StartRetentionCleanup(appCtx, cfg, dbRepo)

	// 3. HTTP Server configuration
	//
	// Every route lives in speaking.NewRouter so the exact production routing
	// table can be built (and asserted on) by tests without binding a port.
	router := speaking.NewRouter(speaking.RouterDeps{
		Config:      cfg,
		Repo:        dbRepo,
		PracticeLLM: practiceLLMClient,
		ExamLLM:     examLLMClient,
		TTS:         ttsClient,
		Langfuse:    langfuseClient,
	})

	server := &http.Server{
		Addr:    ":" + cfg.Port,
		Handler: router,
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
	appCancel()

	// Create shutdown deadline (5 seconds maximum drain window)
	shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer shutdownCancel()

	if err := server.Shutdown(shutdownCtx); err != nil {
		log.Error().Err(err).Msg("HTTP server shutdown error")
	}

	log.Info().Msg("Speaking Service shutdown complete")
}
