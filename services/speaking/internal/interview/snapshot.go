package interview

import "time"

// Snapshot contains only server-owned interview progress. Audio bytes are not
// included; completed audio belongs to its persisted candidate turn, while an
// interrupted in-flight recording is deliberately retried.
type Snapshot struct {
	State             State      `json:"state"`
	Part1Index        int        `json:"part1_index"`
	RoundingIndex     int        `json:"rounding_index"`
	Part3Index        int        `json:"part3_index"`
	Part3Asked        []string   `json:"part3_asked"`
	CurrentQuestionID string     `json:"current_question_id"`
	Deadline          time.Time  `json:"deadline,omitempty"`
	LongTurnStartedAt time.Time  `json:"long_turn_started_at,omitempty"`
	Transcript        Transcript `json:"transcript"`
	TotalCandidateS   float64    `json:"total_candidate_s"`
	NextTurn          int        `json:"next_turn"`
}

func (s *Session) Snapshot() Snapshot {
	asked := make([]string, 0, len(s.part3Asked))
	for id := range s.part3Asked {
		asked = append(asked, id)
	}
	return Snapshot{
		State: s.state, Part1Index: s.part1Index, RoundingIndex: s.roundingIndex,
		Part3Index: s.part3Index, Part3Asked: asked,
		CurrentQuestionID: s.currentQuestionID, Deadline: s.deadline,
		LongTurnStartedAt: s.longTurnStartedAt, Transcript: s.Transcript(),
		TotalCandidateS: s.totalCandidateS, NextTurn: s.nextTurn,
	}
}

func RestoreSession(
	selection Selection,
	timing Timing,
	now func() time.Time,
	sink TurnSink,
	followups *FollowupEngine,
	part3MaxTurns int,
	snapshot Snapshot,
) (*Session, error) {
	session, err := NewAdaptiveSession(selection, timing, now, sink, followups, part3MaxTurns)
	if err != nil {
		return nil, err
	}
	session.state = snapshot.State
	session.part1Index = snapshot.Part1Index
	session.roundingIndex = snapshot.RoundingIndex
	session.part3Index = snapshot.Part3Index
	session.currentQuestionID = snapshot.CurrentQuestionID
	session.deadline = snapshot.Deadline
	session.longTurnStartedAt = snapshot.LongTurnStartedAt
	session.transcript = snapshot.Transcript
	session.totalCandidateS = snapshot.TotalCandidateS
	session.nextTurn = snapshot.NextTurn
	for _, id := range snapshot.Part3Asked {
		session.part3Asked[id] = struct{}{}
	}
	return session, nil
}
