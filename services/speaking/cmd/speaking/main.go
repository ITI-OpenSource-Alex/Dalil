package main

import (
	"net/http"
	"os"

	"github.com/prometheus/client_golang/prometheus/promhttp"
	"github.com/rs/zerolog"
	"github.com/rs/zerolog/log"
	"github.com/ITI-OpenSource-Alex/GOA/services/speaking/internal/speaking"
)

func main() {
	zerolog.TimeFieldFormat = zerolog.TimeFormatUnix
	log.Logger = log.Output(os.Stdout)

	cfg := speaking.LoadConfig()
	log.Info().Str("port", cfg.Port).Int("max_connections", cfg.MaxConnections).Msg("Starting Speaking Service")

	speaking.StartBackgroundTasks()

	http.HandleFunc("/ws", func(w http.ResponseWriter, r *http.Request) {
		speaking.HandleWebSocket(w, r, cfg)
	})

	http.Handle("/metrics", promhttp.Handler())

	log.Fatal().Err(http.ListenAndServe(":"+cfg.Port, nil)).Msg("Server terminated")
}
