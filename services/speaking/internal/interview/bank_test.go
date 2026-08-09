package interview

import (
	"errors"
	"strings"
	"testing"
)

func TestDefaultBankMeetsCoverageAndProvenanceContract(t *testing.T) {
	bank, err := LoadDefaultBank()
	if err != nil {
		t.Fatalf("load default bank: %v", err)
	}
	if bank.BankVersion != "ielts-speaking-bank/2026-08" {
		t.Fatalf("unexpected bank version %q", bank.BankVersion)
	}
	if len(bank.Part1) < 12 || len(bank.Part2) < 20 || len(bank.Part3) < 40 {
		t.Fatalf("bank coverage is too small: part1=%d part2=%d part3=%d", len(bank.Part1), len(bank.Part2), len(bank.Part3))
	}
	if len(bank.SHA256()) != 64 {
		t.Fatalf("bank provenance hash is not SHA-256: %q", bank.SHA256())
	}
}

func TestSelectionIsDeterministicLinkedAndRespectsRepetitionWindow(t *testing.T) {
	bank, err := LoadDefaultBank()
	if err != nil {
		t.Fatal(err)
	}

	first, err := bank.Select("session-123", nil)
	if err != nil {
		t.Fatal(err)
	}
	replay, err := bank.Select("session-123", nil)
	if err != nil {
		t.Fatal(err)
	}
	if first.Cue.CueID != replay.Cue.CueID || first.Part1Topics[0].TopicID != replay.Part1Topics[0].TopicID {
		t.Fatalf("same seed did not replay the same selection: %#v vs %#v", first, replay)
	}
	if first.Part3Seeds[0].ID != first.Cue.Part3Seeds[0] {
		t.Fatalf("Part 3 was not linked to delivered cue: got %q want %q", first.Part3Seeds[0].ID, first.Cue.Part3Seeds[0])
	}

	next, err := bank.Select("session-123", []string{first.Cue.CueID})
	if err != nil {
		t.Fatal(err)
	}
	if next.Cue.CueID == first.Cue.CueID {
		t.Fatalf("cue %q repeated inside exclusion window", first.Cue.CueID)
	}
}

func TestSelectionFailsRatherThanRepeatingWhenEveryCueIsExcluded(t *testing.T) {
	bank, err := LoadDefaultBank()
	if err != nil {
		t.Fatal(err)
	}
	excluded := make([]string, 0, len(bank.Part2))
	for _, cue := range bank.Part2 {
		excluded = append(excluded, cue.CueID)
	}
	_, err = bank.Select("session-123", excluded)
	if !errors.Is(err, ErrNoAvailableCue) {
		t.Fatalf("got %v, want ErrNoAvailableCue", err)
	}
}

func TestBankRejectsUnknownPart3Seed(t *testing.T) {
	data := `{
		"bank_version":"test/v1",
		"part1":[
			{"topic_id":"t1","questions":[{"id":"t1.q1","text":"One?"},{"id":"t1.q2","text":"Two?"}]},
			{"topic_id":"t2","questions":[{"id":"t2.q1","text":"One?"},{"id":"t2.q2","text":"Two?"}]},
			{"topic_id":"t3","questions":[{"id":"t3.q1","text":"One?"},{"id":"t3.q2","text":"Two?"}]}
		],
		"part2":[{"cue_id":"cue","topic":"Topic","prompts":["a","b","c"],"closing_prompt":"why","rounding_off":[{"id":"cue.r1","text":"Round?"}],"part3_seeds":["missing","p3.q1"]}],
		"part3":[{"id":"p3.q1","text":"Discuss?"}]
	}`
	_, err := LoadBank([]byte(data))
	if !errors.Is(err, ErrInvalidBank) || !strings.Contains(err.Error(), "unknown Part 3 seed") {
		t.Fatalf("got %v, want unknown Part 3 seed validation error", err)
	}
}
