package interview

import (
	"context"
	"fmt"
	"strings"
	"testing"
	"time"
)

// TestThreePartInterviewEndToEnd is the black-box gate for the first delivery
// slice: actual embedded bank -> deterministic selection -> every scripted
// Part 1 turn -> enforced Part 2 prep and long turn -> linked Part 3 -> closing.
// It uses no provider, socket, or fake question text.
func TestThreePartInterviewEndToEnd(t *testing.T) {
	bank, err := LoadDefaultBank()
	if err != nil {
		t.Fatal(err)
	}
	selection, err := bank.Select("e2e-session-001", nil)
	if err != nil {
		t.Fatal(err)
	}
	clock := &fakeClock{current: time.Date(2026, 8, 9, 15, 0, 0, 0, time.UTC)}
	sink := &memoryTurnSink{}
	session, err := NewSession(selection, DefaultTiming(), clock.Now, sink)
	if err != nil {
		t.Fatal(err)
	}
	ctx := context.Background()

	assertFrameTypes(t, mustStart(t, ctx, session), "part_change", "examiner_turn")
	assertFrameTypes(t, mustHandle(t, ctx, session, Event{Type: EventReady}), "examiner_turn")

	part1Answers := 0
	for session.State() == StatePart1Question {
		part1Answers++
		frames := mustHandle(t, ctx, session, Event{
			Type: EventAudioEnd,
			Candidate: CandidateTurn{
				Text:      fmt.Sprintf("Candidate answer %d", part1Answers),
				AudioRef:  fmt.Sprintf("s3://speaking/e2e/p1-%02d.webm", part1Answers),
				DurationS: 12,
			},
		})
		if session.State() == StatePart2Cue {
			assertFrameTypes(t, frames, "part_change", "examiner_turn", "cue_card", "examiner_turn")
		}
	}
	if part1Answers != 8 {
		t.Fatalf("Part 1 had %d answers, want 8", part1Answers)
	}
	assertFrameTypes(t, mustHandle(t, ctx, session, Event{Type: EventReady}), "prep_start")

	clock.Advance(60 * time.Second)
	assertFrameTypes(t, mustHandle(t, ctx, session, Event{Type: EventTimerExpired}), "prep_end", "long_turn_start")
	clock.Advance(120 * time.Second)
	assertFrameTypes(t, mustHandle(t, ctx, session, Event{
		Type:      EventTimerExpired,
		Candidate: CandidateTurn{Text: "Sustained Part 2 answer", AudioRef: "s3://speaking/e2e/p2.webm", DurationS: 120},
	}), "examiner_turn")

	// The default bank has one rounding-off question per cue. Its answer moves
	// the session into the two bank-seeded Part 3 questions.
	assertFrameTypes(t, mustHandle(t, ctx, session, Event{
		Type: EventAudioEnd, Candidate: CandidateTurn{Text: "Rounding answer", DurationS: 8},
	}), "part_change", "examiner_turn", "examiner_turn")
	if session.State() != StatePart3Question {
		t.Fatalf("got %s, want part3_question", session.State())
	}

	assertFrameTypes(t, mustHandle(t, ctx, session, Event{
		Type: EventAudioEnd, Candidate: CandidateTurn{Text: "First discussion answer", DurationS: 25},
	}), "examiner_turn")
	frames := mustHandle(t, ctx, session, Event{
		Type: EventAudioEnd, Candidate: CandidateTurn{Text: "Second discussion answer", DurationS: 30},
	})
	assertFrameTypes(t, frames, "examiner_turn", "session_complete")
	if session.State() != StateComplete || frames[1].Partial {
		t.Fatalf("session did not complete normally: state=%s frame=%#v", session.State(), frames[1])
	}

	transcript := session.Transcript()
	if len(transcript.Turns) != len(sink.turns) || len(transcript.Turns) != frames[1].TurnCount {
		t.Fatalf("persistence/transcript/completion counts drifted: transcript=%d sink=%d frame=%d", len(transcript.Turns), len(sink.turns), frames[1].TurnCount)
	}
	candidateText := transcript.CandidateText()
	if strings.Contains(candidateText, introScript) || !strings.Contains(candidateText, "Sustained Part 2 answer") {
		t.Fatalf("candidate-only transcript is contaminated or incomplete: %q", candidateText)
	}
	for _, turn := range transcript.Turns {
		if turn.Speaker == SpeakerCandidate && (turn.Part < 1 || turn.Part > 3 || turn.QuestionID == "") {
			t.Fatalf("candidate evidence is not turn-addressable: %#v", turn)
		}
	}
}

func mustStart(t *testing.T, ctx context.Context, session *Session) []Output {
	t.Helper()
	frames, err := session.Start(ctx)
	if err != nil {
		t.Fatal(err)
	}
	return frames
}

func mustHandle(t *testing.T, ctx context.Context, session *Session, event Event) []Output {
	t.Helper()
	frames, err := session.Handle(ctx, event)
	if err != nil {
		t.Fatal(err)
	}
	return frames
}

func assertFrameTypes(t *testing.T, frames []Output, want ...string) {
	t.Helper()
	if len(frames) != len(want) {
		t.Fatalf("got %d frames %#v, want %d %v", len(frames), frames, len(want), want)
	}
	for i, typ := range want {
		if frames[i].Type != typ {
			t.Fatalf("frame %d type=%q, want %q (all=%#v)", i, frames[i].Type, typ, frames)
		}
	}
}
