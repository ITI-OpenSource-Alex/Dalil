package db

import (
	"context"
	"fmt"
	"io/fs"
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

	for _, name := range entries {
		body, err := fs.ReadFile(files, name)
		if err != nil {
			return fmt.Errorf("reading migration %s: %w", name, err)
		}
		if _, err := tx.Exec(ctx, string(body)); err != nil {
			return fmt.Errorf("applying migration %s: %w", name, err)
		}
	}

	if err := tx.Commit(ctx); err != nil {
		return fmt.Errorf("committing migrations: %w", err)
	}

	log.Info().Int("count", len(entries)).Msg("Speaking service migrations applied successfully")
	return nil
}
