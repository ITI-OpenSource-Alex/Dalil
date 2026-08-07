package db

import (
	"context"
	"fmt"
	"io/fs"
	"os"
	"path"
	"sort"

	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/rs/zerolog/log"
)

// migrationLockID is any stable 64-bit key, distinct from the one the writing
// service uses for writing_db. Shared by every process that migrates speaking_db.
const migrationLockID int64 = 20260727002

// RunMigrations applies every embedded .sql file in filename order, serialised
// across processes by a transaction-scoped advisory lock.
//
// This did not exist before: migrations/001_create_speaking_sessions.sql was
// present in the tree and nothing ever ran it, so speaking_db held zero tables.
// Every completed session logged
//
//	relation "speaking_sessions" does not exist (SQLSTATE 42P01)
//
// as a *non-fatal* error, which meant the client saw a successful evaluation
// while nothing was stored. Every speaking session ever run was lost (BUG-039).
//
// The advisory lock mirrors the writing service's runner and exists for the same
// reason: CREATE TABLE IF NOT EXISTS is not atomic against a concurrent creator,
// so two instances starting on a fresh volume can both see the table missing,
// both create it, and the loser dies on a duplicate pg_class entry. It is a
// cold-start-only failure, which makes it exactly the kind that reaches
// production unnoticed. The lock releases automatically when the transaction
// ends, so the second process waits and then finds the work already done.
func RunMigrations(ctx context.Context, pool *pgxpool.Pool, files fs.FS) error {
	entries, err := fs.Glob(files, "*.sql")
	if err != nil {
		return fmt.Errorf("listing migrations: %w", err)
	}
	if len(entries) == 0 {
		return fmt.Errorf("no migrations found: the embed pattern matched nothing")
	}
	sort.Strings(entries)

	tx, err := pool.Begin(ctx)
	if err != nil {
		return fmt.Errorf("beginning migration transaction: %w", err)
	}
	defer tx.Rollback(ctx)

	if _, err := tx.Exec(ctx, "SELECT pg_advisory_xact_lock($1)", migrationLockID); err != nil {
		return fmt.Errorf("acquiring migration lock: %w", err)
	}
	if _, err := tx.Exec(ctx, `
		CREATE TABLE IF NOT EXISTS migrations_log (
			migration_file VARCHAR(255) PRIMARY KEY,
			executed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
			migration_batch_id VARCHAR(255)
		);
	`); err != nil {
		return fmt.Errorf("creating migrations ledger: %w", err)
	}
	if _, err := tx.Exec(ctx, "ALTER TABLE migrations_log ADD COLUMN IF NOT EXISTS migration_batch_id VARCHAR(255)"); err != nil {
		return fmt.Errorf("ensuring migration batch column: %w", err)
	}

	for _, name := range entries {
		var applied bool
		if err := tx.QueryRow(ctx, "SELECT EXISTS (SELECT 1 FROM migrations_log WHERE migration_file = $1)", name).Scan(&applied); err != nil {
			return fmt.Errorf("checking migration %s: %w", name, err)
		}
		if applied {
			continue
		}
		body, err := fs.ReadFile(files, name)
		if err != nil {
			return fmt.Errorf("reading migration %s: %w", name, err)
		}
		if _, err := tx.Exec(ctx, string(body)); err != nil {
			return fmt.Errorf("applying migration %s: %w", name, err)
		}
		if _, err := tx.Exec(ctx, "INSERT INTO migrations_log (migration_file, migration_batch_id) VALUES ($1, $2)", name, os.Getenv("MIGRATION_BATCH_ID")); err != nil {
			return fmt.Errorf("recording migration %s: %w", name, err)
		}
	}

	if err := tx.Commit(ctx); err != nil {
		return fmt.Errorf("committing migrations: %w", err)
	}

	log.Info().Int("count", len(entries)).Msg("Speaking service migrations applied successfully")
	return nil
}

func RunDownMigrations(ctx context.Context, pool *pgxpool.Pool, files fs.FS) error {
	batchID := os.Getenv("MIGRATION_BATCH_ID")
	if batchID == "" {
		return fmt.Errorf("MIGRATION_BATCH_ID is required for down migrations")
	}

	tx, err := pool.Begin(ctx)
	if err != nil {
		return fmt.Errorf("beginning rollback transaction: %w", err)
	}
	defer tx.Rollback(ctx)

	if _, err := tx.Exec(ctx, "SELECT pg_advisory_xact_lock($1)", migrationLockID); err != nil {
		return fmt.Errorf("acquiring migration lock: %w", err)
	}

	rows, err := tx.Query(ctx, "SELECT migration_file FROM migrations_log WHERE migration_batch_id = $1 ORDER BY migration_file DESC", batchID)
	if err != nil {
		return fmt.Errorf("listing batch migrations: %w", err)
	}
	defer rows.Close()

	rolledBack := 0
	for rows.Next() {
		var migrationFile string
		if err := rows.Scan(&migrationFile); err != nil {
			return fmt.Errorf("reading batch migration row: %w", err)
		}
		rollbackFile := "rollback/" + path.Base(migrationFile[:len(migrationFile)-len(".sql")]) + "_down.sql"
		body, err := fs.ReadFile(files, rollbackFile)
		if err != nil {
			return fmt.Errorf("reading rollback %s: %w", rollbackFile, err)
		}
		if _, err := tx.Exec(ctx, string(body)); err != nil {
			return fmt.Errorf("applying rollback %s: %w", rollbackFile, err)
		}
		if _, err := tx.Exec(ctx, "DELETE FROM migrations_log WHERE migration_file = $1", migrationFile); err != nil {
			return fmt.Errorf("removing migration ledger row %s: %w", migrationFile, err)
		}
		rolledBack++
	}
	if err := rows.Err(); err != nil {
		return fmt.Errorf("iterating batch migrations: %w", err)
	}

	if err := tx.Commit(ctx); err != nil {
		return fmt.Errorf("committing rollbacks: %w", err)
	}

	log.Info().Int("count", rolledBack).Str("batch_id", batchID).Msg("Speaking service migrations rolled back successfully")
	return nil
}
