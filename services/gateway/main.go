package main

import (
	"os"
	"os/signal"
	"syscall"

	"github.com/rs/zerolog"
)

func main() {
	logger := zerolog.New(os.Stdout).With().Timestamp().Logger()

	cfg, err := LoadConfig()
	if err != nil {
		logger.Fatal().Err(err).Msg("failed to load gateway configuration")
	}

	server, err := NewGatewayServer(cfg, logger)
	if err != nil {
		logger.Fatal().Err(err).Msg("failed to create gateway server")
	}

	logger.Info().
		Str("port", cfg.Port).
		Str("version", cfg.Version).
		Msg("starting gateway server")

	serverErrors := make(chan error, 1)
	go func() {
		serverErrors <- server.Listen(":" + cfg.Port)
	}()

	shutdownSignals := make(chan os.Signal, 1)
	signal.Notify(shutdownSignals, syscall.SIGINT, syscall.SIGTERM)
	defer signal.Stop(shutdownSignals)

	select {
	case sig := <-shutdownSignals:
		logger.Info().
			Str("signal", sig.String()).
			Msg("shutdown requested")

		if err := server.Shutdown(); err != nil {
			logger.Error().Err(err).Msg("shutdown failure")
			os.Exit(1)
		}

		logger.Info().Msg("shutdown complete")
	case err := <-serverErrors:
		if err != nil {
			logger.Fatal().Err(err).Msg("gateway server stopped")
		}
	}
}
