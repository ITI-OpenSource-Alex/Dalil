package interview

import (
	"context"
	"errors"
	"fmt"
	"time"
)

type State string

const (
	StateIdle          State = "idle"
	StatePart1Intro    State = "part1_intro"
	StatePart1Question State = "part1_question"
	StatePart2Cue      State = "part2_cue"
	StatePart2Prep     State = "part2_prep"
	StatePart2LongTurn State = "part2_long_turn"
	StatePart2Rounding State = "part2_rounding"
	StatePart3Question State = "part3_question"
	StateComplete      State = "complete"
)

type EventType string

const (
	EventReady        EventType = "ready"
	EventAudioEnd     EventType = "audio_end"
	EventPrepComplete EventType = "prep_complete"
	EventTimerExpired EventType = "timer_expired"
	EventAbandon      EventType = "abandon"
)

var (
	ErrInvalidTransition = errors.New("interview: invalid state transition")
	ErrAudioNotAccepted  = errors.New("interview: current state does not accept candidate audio")
	ErrLongTurnTooShort  = errors.New("interview: long turn minimum has not elapsed")
	ErrTimerNotExpired   = errors.New("interview: authoritative timer has not expired")
	ErrTurnPersistence   = errors.New("interview: persist completed turn")
)

type Event struct {
	Type      EventType
	Candidate CandidateTurn
}

// Output is deliberately shaped like the protocol-v3 JSON frames. The socket
// adapter can marshal it without importing state-machine logic.
type Output struct {
	Type              string    `json:"type"`
	Part              int       `json:"part,omitempty"`
	PartLabel         string    `json:"part_label,omitempty"`
	ExpectedDurationS int       `json:"expected_duration_s,omitempty"`
	TurnID            string    `json:"turn_id,omitempty"`
	QuestionID        string    `json:"question_id,omitempty"`
	Text              string    `json:"text,omitempty"`
	ExpectsResponse   bool      `json:"expects_response,omitempty"`
	CueID             string    `json:"cue_id,omitempty"`
	Topic             string    `json:"topic,omitempty"`
	Prompts           []string  `json:"prompts,omitempty"`
	ClosingPrompt     string    `json:"closing_prompt,omitempty"`
	DurationS         int       `json:"duration_s,omitempty"`
	EndsAt            time.Time `json:"ends_at,omitempty"`
	MinS              int       `json:"min_s,omitempty"`
	MaxS              int       `json:"max_s,omitempty"`
	RemainingS        int       `json:"remaining_s,omitempty"`
	TurnCount         int       `json:"turn_count,omitempty"`
	TotalCandidateS   int       `json:"total_candidate_s,omitempty"`
	Partial           bool      `json:"partial,omitempty"`
}

type Session struct {
	selection Selection
	timing    Timing
	now       func() time.Time
	sink      TurnSink

	state             State
	part1Questions    []Question
	part1Index        int
	roundingIndex     int
	part3Index        int
	part3Asked        map[string]struct{}
	followups         *FollowupEngine
	part3MaxTurns     int
	currentQuestionID string
	deadline          time.Time
	longTurnStartedAt time.Time
	transcript        Transcript
	totalCandidateS   float64
	nextTurn          int
}

func NewSession(selection Selection, timing Timing, now func() time.Time, sink TurnSink) (*Session, error) {
	return NewAdaptiveSession(selection, timing, now, sink, nil, len(selection.Part3Seeds))
}

func NewAdaptiveSession(selection Selection, timing Timing, now func() time.Time, sink TurnSink, followups *FollowupEngine, part3MaxTurns int) (*Session, error) {
	if len(selection.Part1Topics) != 3 || selection.Cue.CueID == "" || len(selection.Part3Seeds) == 0 {
		return nil, fmt.Errorf("%w: incomplete question selection", ErrInvalidTransition)
	}
	if err := timing.Validate(); err != nil {
		return nil, err
	}
	if now == nil {
		now = time.Now
	}
	if part3MaxTurns < len(selection.Part3Seeds) {
		part3MaxTurns = len(selection.Part3Seeds)
	}
	questions := make([]Question, 0)
	for _, topic := range selection.Part1Topics {
		questions = append(questions, topic.Questions...)
	}
	return &Session{
		selection:      selection,
		timing:         timing,
		now:            now,
		sink:           sink,
		state:          StateIdle,
		part1Questions: questions,
		part1Index:     -1,
		roundingIndex:  -1,
		part3Index:     -1,
		part3Asked:     make(map[string]struct{}),
		followups:      followups,
		part3MaxTurns:  part3MaxTurns,
	}, nil
}

func (s *Session) State() State        { return s.state }
func (s *Session) Deadline() time.Time { return s.deadline }
func (s *Session) Transcript() Transcript {
	turns := append([]Turn(nil), s.transcript.Turns...)
	return Transcript{Turns: turns}
}

func (s *Session) Start(ctx context.Context) ([]Output, error) {
	if s.state != StateIdle {
		return nil, ErrInvalidTransition
	}
	turn, frame, err := s.examinerTurn(ctx, 1, "script.part1.intro", introScript, false)
	if err != nil {
		return nil, err
	}
	s.appendTurn(turn)
	s.state = StatePart1Intro
	return []Output{s.partChange(1, s.timing.Part1Expected), frame}, nil
}

func (s *Session) Handle(ctx context.Context, event Event) ([]Output, error) {
	if event.Type == EventAbandon {
		if s.state == StateComplete || s.state == StateIdle {
			return nil, ErrInvalidTransition
		}
		s.state = StateComplete
		return []Output{s.completeFrame(true)}, nil
	}

	switch event.Type {
	case EventReady:
		switch s.state {
		case StatePart1Intro:
			return s.askNextPart1(ctx)
		case StatePart2Cue:
			s.state = StatePart2Prep
			s.deadline = s.now().Add(s.timing.Prep)
			return []Output{{Type: "prep_start", DurationS: seconds(s.timing.Prep), EndsAt: s.deadline}}, nil
		default:
			return nil, ErrInvalidTransition
		}
	case EventPrepComplete:
		if s.state != StatePart2Prep {
			return nil, ErrInvalidTransition
		}
		// Advisory only. The server-owned deadline is unchanged.
		return nil, nil
	case EventTimerExpired:
		return s.handleTimerExpired(ctx, event.Candidate)
	case EventAudioEnd:
		return s.handleAudioEnd(ctx, event.Candidate)
	default:
		return nil, ErrInvalidTransition
	}
}

func (s *Session) handleAudioEnd(ctx context.Context, candidate CandidateTurn) ([]Output, error) {
	switch s.state {
	case StatePart1Question:
		if err := s.persistCandidate(ctx, candidate); err != nil {
			return nil, err
		}
		return s.askNextPart1(ctx)
	case StatePart2Prep:
		return nil, ErrAudioNotAccepted
	case StatePart2LongTurn:
		if s.now().Sub(s.longTurnStartedAt) < s.timing.LongTurnMin {
			return nil, ErrLongTurnTooShort
		}
		if err := s.persistCandidate(ctx, candidate); err != nil {
			return nil, err
		}
		return s.askNextRounding(ctx)
	case StatePart2Rounding:
		if err := s.persistCandidate(ctx, candidate); err != nil {
			return nil, err
		}
		return s.askNextRounding(ctx)
	case StatePart3Question:
		if err := s.persistCandidate(ctx, candidate); err != nil {
			return nil, err
		}
		return s.askNextPart3(ctx, candidate.Text)
	default:
		return nil, ErrAudioNotAccepted
	}
}

func (s *Session) handleTimerExpired(ctx context.Context, candidate CandidateTurn) ([]Output, error) {
	if s.deadline.IsZero() || s.now().Before(s.deadline) {
		return nil, ErrTimerNotExpired
	}
	switch s.state {
	case StatePart2Prep:
		s.state = StatePart2LongTurn
		s.longTurnStartedAt = s.now()
		s.deadline = s.longTurnStartedAt.Add(s.timing.LongTurnMax)
		s.currentQuestionID = s.selection.Cue.CueID
		return []Output{
			{Type: "prep_end"},
			{
				Type: "long_turn_start", MinS: seconds(s.timing.LongTurnMin),
				MaxS: seconds(s.timing.LongTurnMax), EndsAt: s.deadline,
			},
		}, nil
	case StatePart2LongTurn:
		if err := s.persistCandidate(ctx, candidate); err != nil {
			return nil, err
		}
		return s.askNextRounding(ctx)
	default:
		return nil, ErrInvalidTransition
	}
}

func (s *Session) askNextPart1(ctx context.Context) ([]Output, error) {
	nextIndex := s.part1Index + 1
	if nextIndex >= len(s.part1Questions) {
		return s.startPart2(ctx)
	}
	q := s.part1Questions[nextIndex]
	turn, frame, err := s.examinerTurn(ctx, 1, q.ID, q.Text, true)
	if err != nil {
		return nil, err
	}
	s.appendTurn(turn)
	s.part1Index = nextIndex
	s.currentQuestionID = q.ID
	s.state = StatePart1Question
	return []Output{frame}, nil
}

func (s *Session) startPart2(ctx context.Context) ([]Output, error) {
	turn, frame, err := s.examinerTurn(ctx, 2, "script.part2.transition", part2Script, false)
	if err != nil {
		return nil, err
	}
	s.appendTurn(turn)
	cue := s.selection.Cue
	cueTurn, cueFrame, err := s.examinerTurn(ctx, 2, cue.CueID, cueCardScript(cue), false)
	if err != nil {
		return nil, err
	}
	s.appendTurn(cueTurn)
	s.state = StatePart2Cue
	s.deadline = time.Time{}
	return []Output{
		s.partChange(2, s.timing.Part2Expected),
		frame,
		{Type: "cue_card", CueID: cue.CueID, Topic: cue.Topic, Prompts: cue.Prompts, ClosingPrompt: cue.ClosingPrompt},
		cueFrame,
	}, nil
}

func (s *Session) askNextRounding(ctx context.Context) ([]Output, error) {
	nextIndex := s.roundingIndex + 1
	if nextIndex >= len(s.selection.Cue.RoundingOff) {
		return s.startPart3(ctx)
	}
	q := s.selection.Cue.RoundingOff[nextIndex]
	turn, frame, err := s.examinerTurn(ctx, 2, q.ID, q.Text, true)
	if err != nil {
		return nil, err
	}
	s.appendTurn(turn)
	s.roundingIndex = nextIndex
	s.currentQuestionID = q.ID
	s.state = StatePart2Rounding
	s.deadline = time.Time{}
	return []Output{frame}, nil
}

func (s *Session) startPart3(ctx context.Context) ([]Output, error) {
	turn, frame, err := s.examinerTurn(ctx, 3, "script.part3.transition", part3Script, false)
	if err != nil {
		return nil, err
	}
	s.appendTurn(turn)
	s.part3Index = 0
	q := s.selection.Part3Seeds[0]
	questionTurn, questionFrame, err := s.examinerTurn(ctx, 3, q.ID, q.Text, true)
	if err != nil {
		return nil, err
	}
	s.appendTurn(questionTurn)
	s.currentQuestionID = q.ID
	s.part3Asked[q.ID] = struct{}{}
	s.state = StatePart3Question
	return []Output{s.partChange(3, s.timing.Part3Expected), frame, questionFrame}, nil
}

func (s *Session) askNextPart3(ctx context.Context, candidateAnswer string) ([]Output, error) {
	if s.followups != nil {
		if s.part3Index+1 >= s.part3MaxTurns {
			return s.finish(ctx)
		}
		result, err := s.followups.Next(ctx, FollowupRequest{
			CandidateAnswer: candidateAnswer,
			ThemeQuestions:  s.selection.Part3Seeds,
		}, s.part3Index+1, nil)
		if err != nil {
			return nil, err
		}
		if _, repeated := s.part3Asked[result.Question.ID]; repeated {
			return s.finish(ctx)
		}
		turn, frame, err := s.examinerTurn(ctx, 3, result.Question.ID, result.Question.Text, true)
		if err != nil {
			return nil, err
		}
		s.appendTurn(turn)
		s.part3Index++
		s.part3Asked[result.Question.ID] = struct{}{}
		s.currentQuestionID = result.Question.ID
		return []Output{frame}, nil
	}

	nextIndex := s.part3Index + 1
	if nextIndex >= len(s.selection.Part3Seeds) {
		return s.finish(ctx)
	}
	q := s.selection.Part3Seeds[nextIndex]
	turn, frame, err := s.examinerTurn(ctx, 3, q.ID, q.Text, true)
	if err != nil {
		return nil, err
	}
	s.appendTurn(turn)
	s.part3Index = nextIndex
	s.currentQuestionID = q.ID
	return []Output{frame}, nil
}

func (s *Session) finish(ctx context.Context) ([]Output, error) {
	turn, frame, err := s.examinerTurn(ctx, 3, "script.closing", closingScript, false)
	if err != nil {
		return nil, err
	}
	s.appendTurn(turn)
	s.state = StateComplete
	s.currentQuestionID = ""
	return []Output{frame, s.completeFrame(false)}, nil
}

func (s *Session) examinerTurn(ctx context.Context, part int, questionID, text string, expectsResponse bool) (Turn, Output, error) {
	turn := Turn{
		TurnID: s.nextTurnID(), Part: part, QuestionID: questionID,
		Speaker: SpeakerExaminer, Text: text,
	}
	if s.sink != nil {
		if err := s.sink.SaveTurn(ctx, turn); err != nil {
			return Turn{}, Output{}, fmt.Errorf("%w: %v", ErrTurnPersistence, err)
		}
	}
	s.nextTurn++
	return turn, Output{
		Type: "examiner_turn", TurnID: turn.TurnID, Part: part,
		QuestionID: questionID, Text: text, ExpectsResponse: expectsResponse,
	}, nil
}

func (s *Session) persistCandidate(ctx context.Context, candidate CandidateTurn) error {
	duration := candidate.DurationS
	if duration < 0 {
		duration = 0
	}
	turn := Turn{
		TurnID: s.nextTurnID(), Part: s.currentPart(), QuestionID: s.currentQuestionID,
		Speaker: SpeakerCandidate, Text: candidate.Text, AudioRef: candidate.AudioRef,
		Words: candidate.Words, StartS: s.totalCandidateS, EndS: s.totalCandidateS + duration,
	}
	if s.sink != nil {
		if err := s.sink.SaveTurn(ctx, turn); err != nil {
			return fmt.Errorf("%w: %v", ErrTurnPersistence, err)
		}
	}
	s.nextTurn++
	s.totalCandidateS += duration
	s.appendTurn(turn)
	return nil
}

func (s *Session) appendTurn(turn Turn) {
	s.transcript.Turns = append(s.transcript.Turns, turn)
}

func (s *Session) nextTurnID() string {
	return fmt.Sprintf("t%03d", s.nextTurn+1)
}

func (s *Session) currentPart() int {
	switch s.state {
	case StatePart1Question:
		return 1
	case StatePart2LongTurn, StatePart2Rounding, StatePart2Prep:
		return 2
	case StatePart3Question:
		return 3
	default:
		return 0
	}
}

func (s *Session) partChange(part int, expected time.Duration) Output {
	return Output{Type: "part_change", Part: part, PartLabel: partLabel(part), ExpectedDurationS: seconds(expected)}
}

func (s *Session) completeFrame(partial bool) Output {
	return Output{
		Type: "session_complete", TurnCount: len(s.transcript.Turns),
		TotalCandidateS: int(s.totalCandidateS + 0.5), Partial: partial,
	}
}

func seconds(d time.Duration) int { return int(d / time.Second) }
