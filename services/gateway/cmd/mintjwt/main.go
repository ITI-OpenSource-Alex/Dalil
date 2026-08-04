// Command mintjwt prints a Gateway-signed access token.
//
// It exists so the load test and manual QA can drive the REAL authenticated
// path rather than a bypass. It signs with the same TokenService the Gateway
// validates with, so the token goes through the actual JWT middleware,
// blacklist check and revocation-epoch check.
//
//	JWT_SECRET=supersecret_dev_key go run ./cmd/mintjwt
//	JWT_SECRET=... JWT_USER_ID=alice go run ./cmd/mintjwt
//
// The default secret matches docker-compose.yml, so this is a local-development
// tool. It is useless against any environment with a real secret, which is the
// intended limit.
package main

import (
	"fmt"
	"os"
	"time"

	gatewayauth "github.com/ITI-OpenSource-Alex/GOA/services/gateway/auth"
)

func main() {
	secret := os.Getenv("JWT_SECRET")
	if secret == "" {
		secret = "supersecret_dev_key"
	}
	userID := os.Getenv("JWT_USER_ID")
	if userID == "" {
		userID = "perf-user-1"
	}
	ttl := time.Hour
	if raw := os.Getenv("JWT_TTL"); raw != "" {
		if parsed, err := time.ParseDuration(raw); err == nil {
			ttl = parsed
		}
	}

	token, err := gatewayauth.NewTokenService(secret, ttl, 24*time.Hour).
		NewAccessToken(gatewayauth.User{ID: userID, Email: userID + "@example.com"})
	if err != nil {
		fmt.Fprintln(os.Stderr, "mintjwt:", err)
		os.Exit(1)
	}
	fmt.Print(token)
}
