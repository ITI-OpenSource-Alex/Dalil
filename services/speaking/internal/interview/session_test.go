package interview

import (
	"context"
	"errors"
	"testing"
	"time"
)

type fakeClock struct{ current time.Time }

func (f *fakeClock) Now() time.Time          { return f.current }
func (f *fakeClock) Advance(d time.Duration) { f.current = f.current.Add(d) }

type memoryTurnSink struct {
	turns []Turn
	err   error
}

func (m *memoryTurnSink) SaveTurn(_ context.Context, turn Turn) error {
	if m.err != nil {
		return m.err
	}
	m.turns = append(m.turns, turn)
	return nil
}

func newTestSession(t *testing.T) (*Session, *fakeClock, *memoryTurnSink) {
	t.Helper()
	bank, err := LoadDefaultBank()
	if err != nil {
		t.Fatal(err)
	}
	selection, err := bank.Select(t.Name(), nil)
	if err != nil {
		t.Fatal(err)
	}
	clock := &fakeClock{current: time.Date(2026, 8, 9, 12, 0, 0, 0, time.UTC)}
	sink := &memoryTurnSink{}
	session, err := NewSession(selection, DefaultTiming(), clock.Now, sink)
	if err != nil {
		t.Fatal(err)
	}
	return session, clock, sink
}

func TestStartAndReadyEmitPartOneWithoutAssessmentLanguage(t *testing.T) {
	session, _, sink := newTestSession(t)
	ctx := context.Background()

	frames, err := session.Start(ctx)
	if err != nil {
		t.Fatal(err)
	}
	if len(frames) != 2 || frames[0].Type != "part_change" || frames[1].Type != "examiner_turn" {
		t.Fatalf("unexpected start frames: %#v", frames)
	}
	if session.State() != StatePart1Intro || frames[1].ExpectsResponse {
		t.Fatalf("intro state/frame mismatch: state=%s frame=%#v", session.State(), frames[1])
	}

	frames, err = session.Handle(ctx, Event{Type: EventReady})
	if err != nil {
		t.Fatal(err)
	}
	if len(frames) != 1 || !frames[0].ExpectsResponse || session.State() != StatePart1Question {
		t.Fatalf("ready did not ask first scripted question: state=%s frames=%#v", session.State(), frames)
	}
	if len(sink.turns) != 2 || sink.turns[1].QuestionID == "" {
		t.Fatalf("examiner turns were not persisted: %#v", sink.turns)
	}
}

func TestPrepIsServerAuthoritativeAndLongTurnCannotEndEarly(t *testing.T) {
	session, clock, _ := newTestSession(t)
	ctx := context.Background()
	advanceToPart2Prep(t, ctx, session)

	deadline := session.Deadline()
	if _, err := session.Handle(ctx, Event{Type: EventPrepComplete}); err != nil {
		t.Fatalf("advisory prep_complete should be accepted: %v", err)
	}
	if session.State() != StatePart2Prep || session.Deadline() != deadline {
		t.Fatal("client prep_complete changed the authoritative prep deadline")
	}
	if _, err := session.Handle(ctx, Event{Type: EventAudioEnd}); !errors.Is(err, ErrAudioNotAccepted) {
		t.Fatalf("prep accepted candidate audio: %v", err)
	}
	if _, err := session.Handle(ctx, Event{Type: EventTimerExpired}); !errors.Is(err, ErrTimerNotExpired) {
		t.Fatalf("early timer expiry accepted: %v", err)
	}

	clock.Advance(60 * time.Second)
	frames, err := session.Handle(ctx, Event{Type: EventTimerExpired})
	if err != nil {
		t.Fatal(err)
	}
	if session.State() != StatePart2LongTurn || len(frames) != 2 || frames[1].MinS != 60 || frames[1].MaxS != 120 {
		t.Fatalf("prep expiry did not start long turn: state=%s frames=%#v", session.State(), frames)
	}

	clock.Advance(20 * time.Second)
	_, err = session.Handle(ctx, Event{Type: EventAudioEnd, Candidate: CandidateTurn{Text: "Too short", DurationS: 20}})
	if !errors.Is(err, ErrLongTurnTooShort) || session.State() != StatePart2LongTurn {
		t.Fatalf("short long-turn was accepted: state=%s err=%v", session.State(), err)
	}
	// Waiting must not turn a short recording into a valid long turn.
	clock.Advance(40 * time.Second)
	if _, err := session.Handle(ctx, Event{Type: EventAudioEnd, Candidate: CandidateTurn{Text: "Still short", DurationS: 20}}); !errors.Is(err, ErrLongTurnTooShort) {
		t.Fatalf("wall-clock delay incorrectly satisfied speech minimum: %v", err)
	}
	if _, err := session.Handle(ctx, Event{Type: EventAudioEnd, Candidate: CandidateTurn{Text: "Complete long turn", DurationS: 60}}); err != nil {
		t.Fatalf("60-second long turn was rejected: %v", err)
	}
	if session.State() != StatePart2Rounding {
		t.Fatalf("long turn did not advance to rounding: %s", session.State())
	}
}

func TestPart1AndPart3DeadlinesAreAuthoritative(t *testing.T) {
	session, clock, _ := newTestSession(t)
	ctx := context.Background()
	if _, err := session.Start(ctx); err != nil {
		t.Fatal(err)
	}
	if session.Deadline().IsZero() {
		t.Fatal("Part 1 has no server deadline")
	}
	if _, err := session.Handle(ctx, Event{Type: EventReady}); err != nil {
		t.Fatal(err)
	}
	clock.Advance(time.Minute)
	if _, err := session.Handle(ctx, Event{Type: EventTimerExpired}); !errors.Is(err, ErrTimerNotExpired) {
		t.Fatalf("early Part 1 timer accepted: %v", err)
	}
	clock.Advance(4 * time.Minute)
	if _, err := session.Handle(ctx, Event{Type: EventTimerExpired}); err != nil || session.State() != StatePart2Cue {
		t.Fatalf("Part 1 deadline did not advance: state=%s err=%v", session.State(), err)
	}
}

func TestAbandonCompletesPartiallyWithoutInventingMissingTurns(t *testing.T) {
	session, _, _ := newTestSession(t)
	ctx := context.Background()
	if _, err := session.Start(ctx); err != nil {
		t.Fatal(err)
	}
	if _, err := session.Handle(ctx, Event{Type: EventReady}); err != nil {
		t.Fatal(err)
	}
	before := len(session.Transcript().Turns)
	frames, err := session.Handle(ctx, Event{Type: EventAbandon})
	if err != nil {
		t.Fatal(err)
	}
	if session.State() != StateComplete || len(frames) != 1 || !frames[0].Partial {
		t.Fatalf("abandon did not produce partial completion: state=%s frames=%#v", session.State(), frames)
	}
	if len(session.Transcript().Turns) != before {
		t.Fatal("abandon fabricated missing turns")
	}
}

func TestPersistenceFailureStopsTransition(t *testing.T) {
	session, _, sink := newTestSession(t)
	sink.err = errors.New("database unavailable")
	_, err := session.Start(context.Background())
	if !errors.Is(err, ErrTurnPersistence) {
		t.Fatalf("got %v, want ErrTurnPersistence", err)
	}
	if session.State() != StateIdle || len(session.Transcript().Turns) != 0 {
		t.Fatalf("failed persisted turn changed state: state=%s transcript=%#v", session.State(), session.Transcript())
	}

	// A retry reuses the uncommitted turn id rather than leaving a provenance
	// gap or changing the selected question.
	sink.err = nil
	frames, err := session.Start(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if frames[1].TurnID != "t001" || sink.turns[0].TurnID != "t001" {
		t.Fatalf("retry changed the first turn id: frames=%#v sink=%#v", frames, sink.turns)
	}
}

func TestSnapshotRestoresAtTheNextQuestionWithoutLosingTurns(t *testing.T) {
	session, clock, sink := newTestSession(t)
	ctx := context.Background()
	if _, err := session.Start(ctx); err != nil {
		t.Fatal(err)
	}
	if _, err := session.Handle(ctx, Event{Type: EventReady}); err != nil {
		t.Fatal(err)
	}
	if _, err := session.Handle(ctx, Event{Type: EventAudioEnd, Candidate: CandidateTurn{Text: "First answer", DurationS: 9}}); err != nil {
		t.Fatal(err)
	}

	restored, err := RestoreSession(session.selection, session.timing, clock.Now, sink, nil, len(session.selection.Part3Seeds), session.Snapshot())
	if err != nil {
		t.Fatal(err)
	}
	if restored.State() != session.State() || restored.currentQuestionID != session.currentQuestionID {
		t.Fatalf("resume drifted: original=%s/%s restored=%s/%s", session.State(), session.currentQuestionID, restored.State(), restored.currentQuestionID)
	}
	if restored.Transcript().CandidateText() != "First answer" || restored.nextTurn != session.nextTurn {
		t.Fatalf("resume lost evidence or provenance: %#v", restored.Snapshot())
	}
}

func advanceToPart2Prep(t *testing.T, ctx context.Context, session *Session) {
	t.Helper()
	if _, err := session.Start(ctx); err != nil {
		t.Fatal(err)
	}
	if _, err := session.Handle(ctx, Event{Type: EventReady}); err != nil {
		t.Fatal(err)
	}
	for session.State() == StatePart1Question {
		if _, err := session.Handle(ctx, Event{
			Type:      EventAudioEnd,
			Candidate: CandidateTurn{Text: "Part one answer", AudioRef: "memory://part1", DurationS: 10},
		}); err != nil {
			t.Fatal(err)
		}
	}
	if session.State() != StatePart2Cue {
		t.Fatalf("got %s, want part2_cue", session.State())
	}
	if _, err := session.Handle(ctx, Event{Type: EventReady}); err != nil {
		t.Fatal(err)
	}
	if session.State() != StatePart2Prep {
		t.Fatalf("got %s, want part2_prep", session.State())
	}
}
