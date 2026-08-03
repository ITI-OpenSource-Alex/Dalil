package speaking

import (
	"context"
	"time"

	"github.com/ITI-OpenSource-Alex/GOA/services/speaking/db"
	"github.com/rs/zerolog/log"
)

func StartRetentionCleanup(ctx context.Context, cfg *Config, repo db.Repository) {
	interval := time.Duration(cfg.RetentionCleanupIntervalHour) * time.Hour
	if interval <= 0 {
		log.Warn().Msg("Speaking retention cleanup disabled")
		return
	}

	go func() {
		runSpeakingRetentionCleanup(ctx, repo)
		ticker := time.NewTicker(interval)
		defer ticker.Stop()

		for {
			select {
			case <-ctx.Done():
				log.Info().Msg("Speaking retention cleanup stopped")
				return
			case <-ticker.C:
				runSpeakingRetentionCleanup(ctx, repo)
			}
		}
	}()
}

func runSpeakingRetentionCleanup(ctx context.Context, repo db.Repository) {
	cutoff := time.Now().UTC().AddDate(-1, 0, 0)
	deleted, err := repo.DeleteOlderThan(ctx, cutoff)
	if err != nil {
		log.Error().Err(err).Time("cutoff", cutoff).Msg("Speaking retention cleanup failed")
		return
	}
	log.Info().Int64("deleted", deleted).Time("cutoff", cutoff).Msg("Speaking retention cleanup completed")
}
