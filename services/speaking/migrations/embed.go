// Package migrations carries the speaking service's SQL migrations, embedded in
// the binary.
//
// Embedding rather than reading from disk is deliberate. The production stage of
// the Dockerfile copies only the compiled binary:
//
//	COPY --from=builder /speaking .
//
// so a runner that opened ./migrations would work in dev — where the source tree
// is bind-mounted — and fail in production, which is the worst possible split.
// It also keeps working under GOA-031's Lambda migration, where there is no
// meaningful working directory at all.
package migrations

import "embed"

// FS holds every .sql file in this directory, applied in filename order.
//
//go:embed *.sql
var FS embed.FS
