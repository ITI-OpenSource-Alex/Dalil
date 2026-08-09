package interview

import (
	"crypto/sha256"
	"encoding/binary"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"math/rand"
)

var (
	ErrInvalidBank      = errors.New("interview: invalid question bank")
	ErrNoAvailableCue   = errors.New("interview: no cue card remains outside the repetition window")
	ErrEmptySessionSeed = errors.New("interview: session seed is required")
)

type Question struct {
	ID   string `json:"id"`
	Text string `json:"text"`
}

type Part1Topic struct {
	TopicID   string     `json:"topic_id"`
	Questions []Question `json:"questions"`
}

type CueCard struct {
	CueID         string     `json:"cue_id"`
	Topic         string     `json:"topic"`
	Prompts       []string   `json:"prompts"`
	ClosingPrompt string     `json:"closing_prompt"`
	RoundingOff   []Question `json:"rounding_off"`
	Part3Seeds    []string   `json:"part3_seeds"`
}

type Bank struct {
	BankVersion string       `json:"bank_version"`
	Part1       []Part1Topic `json:"part1"`
	Part2       []CueCard    `json:"part2"`
	Part3       []Question   `json:"part3"`
	hash        string
}

type Selection struct {
	BankVersion string
	BankSHA256  string
	Part1Topics []Part1Topic
	Cue         CueCard
	Part3Seeds  []Question
}

func LoadBank(data []byte) (*Bank, error) {
	var bank Bank
	if err := json.Unmarshal(data, &bank); err != nil {
		return nil, fmt.Errorf("%w: decode JSON: %v", ErrInvalidBank, err)
	}
	if err := bank.Validate(); err != nil {
		return nil, err
	}
	digest := sha256.Sum256(data)
	bank.hash = hex.EncodeToString(digest[:])
	return &bank, nil
}

func (b *Bank) SHA256() string {
	if b == nil {
		return ""
	}
	return b.hash
}

func (b *Bank) Validate() error {
	if b == nil || b.BankVersion == "" {
		return fmt.Errorf("%w: bank_version is required", ErrInvalidBank)
	}
	if len(b.Part1) < 3 || len(b.Part2) == 0 || len(b.Part3) == 0 {
		return fmt.Errorf("%w: bank needs at least 3 Part 1 topics and non-empty Parts 2 and 3", ErrInvalidBank)
	}

	ids := make(map[string]struct{})
	claimID := func(id, kind string) error {
		if id == "" {
			return fmt.Errorf("%w: %s id is required", ErrInvalidBank, kind)
		}
		if _, exists := ids[id]; exists {
			return fmt.Errorf("%w: duplicate id %q", ErrInvalidBank, id)
		}
		ids[id] = struct{}{}
		return nil
	}

	for _, topic := range b.Part1 {
		if err := claimID(topic.TopicID, "Part 1 topic"); err != nil {
			return err
		}
		if len(topic.Questions) < 2 {
			return fmt.Errorf("%w: topic %q needs at least 2 questions", ErrInvalidBank, topic.TopicID)
		}
		for _, q := range topic.Questions {
			if q.Text == "" {
				return fmt.Errorf("%w: question %q has empty text", ErrInvalidBank, q.ID)
			}
			if err := claimID(q.ID, "Part 1 question"); err != nil {
				return err
			}
		}
	}

	part3ByID := make(map[string]Question, len(b.Part3))
	for _, q := range b.Part3 {
		if q.Text == "" {
			return fmt.Errorf("%w: question %q has empty text", ErrInvalidBank, q.ID)
		}
		if err := claimID(q.ID, "Part 3 question"); err != nil {
			return err
		}
		part3ByID[q.ID] = q
	}

	for _, cue := range b.Part2 {
		if err := claimID(cue.CueID, "Part 2 cue"); err != nil {
			return err
		}
		if cue.Topic == "" || cue.ClosingPrompt == "" || len(cue.Prompts) != 3 {
			return fmt.Errorf("%w: cue %q must have a topic, exactly 3 prompts, and a closing prompt", ErrInvalidBank, cue.CueID)
		}
		if len(cue.RoundingOff) < 1 || len(cue.RoundingOff) > 2 {
			return fmt.Errorf("%w: cue %q needs 1 or 2 rounding-off questions", ErrInvalidBank, cue.CueID)
		}
		for _, q := range cue.RoundingOff {
			if q.Text == "" {
				return fmt.Errorf("%w: rounding question %q has empty text", ErrInvalidBank, q.ID)
			}
			if err := claimID(q.ID, "Part 2 rounding question"); err != nil {
				return err
			}
		}
		if len(cue.Part3Seeds) < 2 {
			return fmt.Errorf("%w: cue %q needs at least 2 Part 3 seeds", ErrInvalidBank, cue.CueID)
		}
		for _, seedID := range cue.Part3Seeds {
			if _, ok := part3ByID[seedID]; !ok {
				return fmt.Errorf("%w: cue %q references unknown Part 3 seed %q", ErrInvalidBank, cue.CueID, seedID)
			}
		}
	}

	return nil
}

// Select deterministically chooses three distinct Part 1 topics and one cue
// card. recentlyUsedCueIDs is the caller-owned repetition window; selection
// never silently falls back to a repeated card.
func (b *Bank) Select(sessionSeed string, recentlyUsedCueIDs []string) (Selection, error) {
	if sessionSeed == "" {
		return Selection{}, ErrEmptySessionSeed
	}
	if err := b.Validate(); err != nil {
		return Selection{}, err
	}

	digest := sha256.Sum256([]byte(sessionSeed))
	rng := rand.New(rand.NewSource(int64(binary.LittleEndian.Uint64(digest[:8]))))
	permutation := rng.Perm(len(b.Part1))
	topics := make([]Part1Topic, 0, 3)
	for _, index := range permutation[:3] {
		topics = append(topics, b.Part1[index])
	}

	recent := make(map[string]struct{}, len(recentlyUsedCueIDs))
	for _, id := range recentlyUsedCueIDs {
		recent[id] = struct{}{}
	}
	available := make([]CueCard, 0, len(b.Part2))
	for _, cue := range b.Part2 {
		if _, excluded := recent[cue.CueID]; !excluded {
			available = append(available, cue)
		}
	}
	if len(available) == 0 {
		return Selection{}, ErrNoAvailableCue
	}
	cue := available[rng.Intn(len(available))]

	part3ByID := make(map[string]Question, len(b.Part3))
	for _, q := range b.Part3 {
		part3ByID[q.ID] = q
	}
	seeds := make([]Question, 0, len(cue.Part3Seeds))
	for _, id := range cue.Part3Seeds {
		seeds = append(seeds, part3ByID[id])
	}

	return Selection{
		BankVersion: b.BankVersion,
		BankSHA256:  b.SHA256(),
		Part1Topics: topics,
		Cue:         cue,
		Part3Seeds:  seeds,
	}, nil
}
