// Command score-transcript runs the real evaluation swarm over a transcript and
// prints the canonical evaluation as JSON.
//
// This is the scorer-only lane's entry point (SPEAK-EVAL-007). It exists so the
// benchmark scores through the PRODUCTION path -- the same prompts, the same
// frozen rubric, the same four agents, the same aggregation and the same
// half-band rounding that a student's practice session uses. A Python
// reimplementation would have been quicker to write and would have measured a
// second scorer that merely resembles the first, which is the one result nobody
// wants.
//
//	score-transcript --transcript path.txt --item-id yt-abc [--question "..."]
//
// Prosody is deliberately absent: this lane has a transcript and no audio, so
// features are nil and the Fluency agent says so itself rather than inventing
// acoustic evidence (GOA-133).
package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"strings"
	"time"

	"github.com/ITI-OpenSource-Alex/GOA/services/speaking/agents"
	"github.com/ITI-OpenSource-Alex/GOA/services/speaking/internal/contract"
	"github.com/ITI-OpenSource-Alex/GOA/services/speaking/llm"
	"github.com/rs/zerolog"
	"github.com/rs/zerolog/log"
)

func main() {
	transcriptPath := flag.String("transcript", "", "file containing the candidate transcript")
	itemID := flag.String("item-id", "", "benchmark item id, recorded in provenance")
	question := flag.String("question", "IELTS Speaking interview", "question prompt given to the candidate")
	questionType := flag.String("question-type", "part1", "part1, part2 or part3")
	timeout := flag.Duration("timeout", 120*time.Second, "swarm deadline")
	flag.Parse()

	// Quiet by default: stdout carries JSON that a caller parses, so anything
	// chatty on stdout would corrupt it. Diagnostics go to stderr.
	zerolog.SetGlobalLevel(zerolog.WarnLevel)
	log.Logger = log.Output(os.Stderr)

	if *transcriptPath == "" || *itemID == "" {
		fmt.Fprintln(os.Stderr, "usage: score-transcript --transcript <file> --item-id <id>")
		os.Exit(2)
	}

	raw, err := os.ReadFile(*transcriptPath)
	if err != nil {
		fmt.Fprintf(os.Stderr, "score-transcript: %v\n", err)
		os.Exit(2)
	}
	transcript := strings.TrimSpace(string(raw))
	if transcript == "" {
		// An empty transcript must not be scored. BUG-035 and the browser-audio
		// defect both ended with the swarm grading nothing and returning a band
		// for it; refusing here is cheaper than detecting it downstream.
		fmt.Fprintln(os.Stderr, "score-transcript: transcript is empty; refusing to score")
		os.Exit(2)
	}

	model := envOr("SPEAKING_PRACTICE_MODEL", envOr("LLM_MODEL", "claude-opus-4-8"))
	apiKey := envOr("ANTHROPIC_AUTH_TOKEN", os.Getenv("ANTHROPIC_API_KEY"))
	baseURL := envOr("GOA_LLM_BASE_URL", os.Getenv("ANTHROPIC_BASE_URL"))
	if apiKey == "" {
		fmt.Fprintln(os.Stderr, "score-transcript: no ANTHROPIC_AUTH_TOKEN or ANTHROPIC_API_KEY")
		os.Exit(2)
	}

	client := llm.NewClient(model, apiKey, baseURL)

	ctx, cancel := context.WithTimeout(context.Background(), *timeout)
	defer cancel()

	started := time.Now()
	result, swarmErr := agents.EvaluateSwarm(
		ctx, client, *question, *questionType, transcript,
		nil, // no audio in this lane, so no prosody -- never zeros
		nil,
	)

	evaluation := agents.CanonicalizeSwarm(result, agents.CanonicalMeta{
		EvaluationID:  *itemID,
		Mode:          contract.ModeBenchmark, // never mistakable for a user's result
		CreatedAt:     time.Now().UTC(),
		ScorerVersion: envOr("GOA_SCORER_VERSION", "speaking@dev"),
		LLMProvider:   "agentrouter",
		LLMModel:      model,
	})

	out := map[string]any{
		"evaluation":  evaluation,
		"latency_ms":  time.Since(started).Milliseconds(),
		"swarm_error": errString(swarmErr),
	}

	encoder := json.NewEncoder(os.Stdout)
	encoder.SetIndent("", "  ")
	if err := encoder.Encode(out); err != nil {
		fmt.Fprintf(os.Stderr, "score-transcript: %v\n", err)
		os.Exit(1)
	}

	// A swarm error is reported in the payload AND in the exit code. The caller
	// records the item as failed rather than reading a band off it.
	if swarmErr != nil {
		os.Exit(1)
	}
}

func envOr(key, fallback string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return fallback
}

func errString(err error) string {
	if err == nil {
		return ""
	}
	return err.Error()
}
