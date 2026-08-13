package interview

import (
	"context"
	"strings"
)

type Speaker string

const (
	SpeakerExaminer  Speaker = "examiner"
	SpeakerCandidate Speaker = "candidate"
)

type WordTiming struct {
	Word        string  `json:"word"`
	StartS      float64 `json:"start_s"`
	EndS        float64 `json:"end_s"`
	Probability float64 `json:"probability,omitempty"`
}

type Turn struct {
	TurnID     string       `json:"turn_id"`
	Part       int          `json:"part"`
	QuestionID string       `json:"question_id"`
	Speaker    Speaker      `json:"speaker"`
	Text       string       `json:"text"`
	StartS     float64      `json:"start_s,omitempty"`
	EndS       float64      `json:"end_s,omitempty"`
	AudioRef   string       `json:"audio_ref,omitempty"`
	Words      []WordTiming `json:"words,omitempty"`
}

type CandidateTurn struct {
	Text      string
	AudioRef  string
	Words     []WordTiming
	DurationS float64
}

type TurnSink interface {
	SaveTurn(context.Context, Turn) error
}

type Transcript struct {
	Turns []Turn `json:"turns"`
}

func (t Transcript) CandidateText() string {
	parts := make([]string, 0, len(t.Turns))
	for _, turn := range t.Turns {
		if turn.Speaker == SpeakerCandidate && strings.TrimSpace(turn.Text) != "" {
			parts = append(parts, strings.TrimSpace(turn.Text))
		}
	}
	return strings.Join(parts, "\n")
}
