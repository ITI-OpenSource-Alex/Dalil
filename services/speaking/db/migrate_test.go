package db

import (
	"context"
	"fmt"
	"math/rand"
	"os"
	"testing"
	"time"

	"github.com/ITI-OpenSource-Alex/GOA/services/speaking/migrations"
	"github.com/jackc/pgx/v5/pgxpool"
)

// The migrations have to be applied to a real Postgres to be worth anything.
//
// Every other test in this package drives pgxmock, which validates the SQL this
// service *sends* and says nothing about the schema it *needs*. That gap let
// 004 ship with `session_id TEXT` referencing `speaking_sessions.id UUID` —
// which Postgres rejects with SQLSTATE 42804. The runner applies every
// migration in a single transaction and main() calls log.Fatal when it fails,
// so one bad type annotation rolled back 001-005 and kept the entire Speaking
// service from starting. No unit test could have caught it.
//
// Skipped unless a server is reachable, so `go test ./...` stays hermetic:
//
//	SPEAKING_TEST_DATABASE_URL=postgres://goa:goa_pass@localhost:5432/postgres go test ./db/
//
// The URL may point at any database on the server; the test creates and drops
// its own so it never touches real data.
func TestMigrationsApplyToRealPostgres(t *testing.T) {
	adminURL := os.Getenv("SPEAKING_TEST_DATABASE_URL")
	if adminURL == "" {
		t.Skip("SPEAKING_TEST_DATABASE_URL is not set; skipping the real-Postgres migration check")
	}

	ctx, cancel := context.WithTimeout(context.Background(), 60*time.Second)
	defer cancel()

	admin, err := pgxpool.New(ctx, adminURL)
	if err != nil {
		t.Fatalf("connecting to %s: %v", adminURL, err)
	}
	// t.Cleanup rather than defer: cleanups run after the deferred calls in this
	// function, so a deferred Close would shut the admin pool before the DROP
	// below ever ran. Registered first so it runs last (cleanups are LIFO).
	t.Cleanup(admin.Close)
	if err := admin.Ping(ctx); err != nil {
		t.Skipf("no Postgres at SPEAKING_TEST_DATABASE_URL: %v", err)
	}

	// A throwaway database, so this proves a cold start rather than finding the
	// tables already there from a previous run.
	name := fmt.Sprintf("speaking_migrations_test_%d_%d", time.Now().UnixNano(), rand.Intn(1000))
	if _, err := admin.Exec(ctx, "CREATE DATABASE "+name); err != nil {
		t.Fatalf("creating scratch database: %v", err)
	}
	t.Cleanup(func() {
		dropCtx, dropCancel := context.WithTimeout(context.Background(), 30*time.Second)
		defer dropCancel()
		if _, err := admin.Exec(dropCtx, "DROP DATABASE IF EXISTS "+name+" WITH (FORCE)"); err != nil {
			t.Logf("could not drop scratch database %s: %v", name, err)
		}
	})

	scratchURL := replaceDatabase(adminURL, name)
	pool, err := pgxpool.New(ctx, scratchURL)
	if err != nil {
		t.Fatalf("connecting to the scratch database: %v", err)
	}
	t.Cleanup(pool.Close)

	if err := RunMigrations(ctx, pool, migrations.FS); err != nil {
		t.Fatalf("migrations failed against a real Postgres: %v", err)
	}

	// Re-running must be a no-op: the service migrates on every boot.
	if err := RunMigrations(ctx, pool, migrations.FS); err != nil {
		t.Fatalf("migrations are not idempotent: %v", err)
	}

	// The tables the interview socket writes to on its very first turn. A
	// migration set that "succeeds" without these would still leave the
	// examiner unable to speak.
	for _, table := range []string{
		"speaking_sessions", "speaking_explanations",
		"speaking_interview_sessions", "speaking_interview_turns",
	} {
		var exists bool
		if err := pool.QueryRow(ctx,
			"SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = $1)",
			table,
		).Scan(&exists); err != nil {
			t.Fatalf("checking for %s: %v", table, err)
		}
		if !exists {
			t.Errorf("%s was not created", table)
		}
	}
}

// replaceDatabase swaps the database in a Postgres URL, keeping credentials,
// host and query parameters intact.
func replaceDatabase(rawURL, database string) string {
	scheme, rest, found := cut(rawURL, "://")
	if !found {
		return rawURL
	}
	authority, tail, hasPath := cut(rest, "/")
	if !hasPath {
		return scheme + "://" + rest + "/" + database
	}
	_, query, hasQuery := cut(tail, "?")
	if hasQuery {
		return scheme + "://" + authority + "/" + database + "?" + query
	}
	return scheme + "://" + authority + "/" + database
}

func cut(s, sep string) (before, after string, found bool) {
	for i := 0; i+len(sep) <= len(s); i++ {
		if s[i:i+len(sep)] == sep {
			return s[:i], s[i+len(sep):], true
		}
	}
	return s, "", false
}
