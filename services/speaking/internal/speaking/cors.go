// internal/speaking/cors.go
package speaking

import "net/http"

// WithCORS wraps a handler so it can be called directly from the browser
// (the frontend fetches /sessions* endpoints straight from this service,
// the same way it connects directly to /ws — see speaking-websocket.ts).
// Without these headers the browser blocks the response even though the
// HTTP request itself succeeds, so this must wrap every browser-facing
// endpoint. Preflight OPTIONS requests are answered directly with no body.
func WithCORS(next http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Access-Control-Allow-Origin", "*")
		w.Header().Set("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
		w.Header().Set("Access-Control-Allow-Headers", "Content-Type")

		if r.Method == http.MethodOptions {
			w.WriteHeader(http.StatusNoContent)
			return
		}

		next(w, r)
	}
}
