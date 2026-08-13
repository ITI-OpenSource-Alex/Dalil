package interview

import (
	"context"
	"errors"
	"testing"
)

type sequenceGenerator struct {
	responses []string
	errors    []error
	calls     int
}

func (g *sequenceGenerator) GenerateFollowup(_ context.Context, _ FollowupRequest) (string, error) {
	index := g.calls
	g.calls++
	if index < len(g.errors) && g.errors[index] != nil {
		return "", g.errors[index]
	}
	if index < len(g.responses) {
		return g.responses[index], nil
	}
	return "", nil
}

type fixedTopicChecker struct {
	onTopic bool
	err     error
}

func (c fixedTopicChecker) OnTopic(context.Context, string, []Question) (bool, error) {
	return c.onTopic, c.err
}

func TestFollowupValidationRejectsContaminatingQuestions(t *testing.T) {
	tests := []struct {
		name          string
		text          string
		withheldLexis []string
		maximumWords  int
	}{
		{name: "two questions", text: "Why is that? What changed?"},
		{name: "two sentences", text: "That is interesting. Why did it change?"},
		{name: "assessment", text: "Good answer, why is that important?"},
		{name: "correction", text: "You should say sustainable, why does it matter?"},
		{name: "leading", text: "Don't you think public transport is better?"},
		{name: "lexical gift", text: "How could governments improve sustainability?", withheldLexis: []string{"sustainability"}},
		{name: "too long", text: "Why do people in large modern cities often choose to use private cars even when convenient public transport is readily available to them?", maximumWords: 12},
	}

	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			maxWords := test.maximumWords
			if maxWords == 0 {
				maxWords = defaultFollowupMaxWords
			}
			if err := validateFollowup(test.text, FollowupPolicy{MaxWords: maxWords}, test.withheldLexis); err == nil {
				t.Fatalf("question was accepted: %q", test.text)
			}
		})
	}
}

func TestFollowupEngineRegeneratesOnceThenUsesBankFallback(t *testing.T) {
	generator := &sequenceGenerator{responses: []string{
		"Excellent answer, wouldn't you agree that schools are best?",
		"What changes might education experience in the future?",
	}}
	engine := FollowupEngine{
		Generator: generator, TopicChecker: fixedTopicChecker{onTopic: false},
		Policy: DefaultFollowupPolicy(),
	}
	fallback := Question{ID: "p3.education.q2", Text: "How might education change in the future?"}

	result, err := engine.Next(context.Background(), FollowupRequest{
		CandidateAnswer: "Online learning is more flexible.",
		ThemeQuestions:  []Question{{ID: "p3.education.q1", Text: "How has education changed?"}, fallback},
	}, 1, nil)
	if err != nil {
		t.Fatal(err)
	}
	if generator.calls != 2 || result.Generated || result.Question != fallback {
		t.Fatalf("unexpected bounded fallback: calls=%d result=%#v", generator.calls, result)
	}
}

func TestFollowupEngineAcceptsValidatedOnTopicQuestion(t *testing.T) {
	generator := &sequenceGenerator{responses: []string{"Why might flexibility matter to adult learners?"}}
	engine := FollowupEngine{
		Generator: generator, TopicChecker: fixedTopicChecker{onTopic: true},
		Policy: DefaultFollowupPolicy(),
	}

	result, err := engine.Next(context.Background(), FollowupRequest{
		CandidateAnswer: "Online learning is more flexible.",
		ThemeQuestions:  []Question{{ID: "p3.education.q1", Text: "How has education changed?"}},
	}, 0, nil)
	if err != nil {
		t.Fatal(err)
	}
	if !result.Generated || result.Question.Text != "Why might flexibility matter to adult learners?" || result.Question.ID == "" {
		t.Fatalf("validated question was not accepted: %#v", result)
	}
}

func TestFollowupEngineNeverStallsOnGeneratorOrTopicFailure(t *testing.T) {
	fallback := Question{ID: "p3.work.q1", Text: "How has work changed?"}
	generator := &sequenceGenerator{errors: []error{errors.New("timeout"), errors.New("timeout")}}
	engine := FollowupEngine{
		Generator: generator, TopicChecker: fixedTopicChecker{err: errors.New("embedding unavailable")},
		Policy: DefaultFollowupPolicy(),
	}

	result, err := engine.Next(context.Background(), FollowupRequest{ThemeQuestions: []Question{fallback}}, 0, nil)
	if err != nil || result.Question != fallback || result.Generated {
		t.Fatalf("provider failure did not use fallback: result=%#v err=%v", result, err)
	}

	_, err = engine.Next(context.Background(), FollowupRequest{}, 0, nil)
	if !errors.Is(err, ErrNoPart3Fallback) {
		t.Fatalf("got %v, want ErrNoPart3Fallback", err)
	}
}
