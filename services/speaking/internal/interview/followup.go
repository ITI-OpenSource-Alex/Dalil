package interview

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"strings"
	"time"
	"unicode"
)

const defaultFollowupMaxWords = 24

var ErrNoPart3Fallback = errors.New("interview: no Part 3 fallback question")

type FollowupRequest struct {
	CandidateAnswer string
	ThemeQuestions  []Question
}

// FollowupGenerator is deliberately narrower than the scoring model. Its
// implementation must not receive a rubric, score, or criterion output.
type FollowupGenerator interface {
	GenerateFollowup(context.Context, FollowupRequest) (string, error)
}

// TopicChecker keeps topic matching replaceable without coupling the interview
// package to an embedding provider. A provider failure rejects the generated
// question and therefore takes the bank fallback path.
type TopicChecker interface {
	OnTopic(context.Context, string, []Question) (bool, error)
}

type FollowupPolicy struct {
	MaxWords int
}

func DefaultFollowupPolicy() FollowupPolicy {
	return FollowupPolicy{MaxWords: defaultFollowupMaxWords}
}

type FollowupEngine struct {
	Generator    FollowupGenerator
	TopicChecker TopicChecker
	Policy       FollowupPolicy
	Timeout      time.Duration
}

type FollowupResult struct {
	Question  Question
	Generated bool
}

// Next tries at most twice to produce a bounded adaptive question. Any model,
// validation, or topic-checking failure falls back to the requested bank seed;
// the interview never stalls because generation failed.
func (e FollowupEngine) Next(
	ctx context.Context,
	request FollowupRequest,
	fallbackIndex int,
	withheldLexis []string,
) (FollowupResult, error) {
	if e.Timeout > 0 {
		var cancel context.CancelFunc
		ctx, cancel = context.WithTimeout(ctx, e.Timeout)
		defer cancel()
	}
	fallback, err := part3Fallback(request.ThemeQuestions, fallbackIndex)
	if err != nil {
		return FollowupResult{}, err
	}
	if e.Generator == nil || e.TopicChecker == nil {
		return FollowupResult{Question: fallback}, nil
	}

	policy := e.Policy
	if policy.MaxWords <= 0 {
		policy = DefaultFollowupPolicy()
	}
	for attempt := 0; attempt < 2; attempt++ {
		text, generateErr := e.Generator.GenerateFollowup(ctx, request)
		if generateErr != nil {
			continue
		}
		text = strings.TrimSpace(text)
		if validateFollowup(text, policy, withheldLexis) != nil {
			continue
		}
		onTopic, topicErr := e.TopicChecker.OnTopic(ctx, text, request.ThemeQuestions)
		if topicErr != nil || !onTopic {
			continue
		}
		digest := sha256.Sum256([]byte(text))
		return FollowupResult{
			Question:  Question{ID: "p3.generated." + hex.EncodeToString(digest[:6]), Text: text},
			Generated: true,
		}, nil
	}

	return FollowupResult{Question: fallback}, nil
}

func part3Fallback(questions []Question, index int) (Question, error) {
	if len(questions) == 0 {
		return Question{}, ErrNoPart3Fallback
	}
	if index < 0 {
		index = 0
	}
	return questions[index%len(questions)], nil
}

func validateFollowup(text string, policy FollowupPolicy, withheldLexis []string) error {
	if text == "" || strings.Count(text, "?") != 1 || !strings.HasSuffix(text, "?") {
		return errors.New("follow-up must be exactly one question")
	}
	terminalMarks := 0
	for _, r := range text {
		if r == '?' || r == '!' || r == '.' {
			terminalMarks++
		}
	}
	if terminalMarks != 1 {
		return errors.New("follow-up must be one sentence")
	}
	if countWords(text) > policy.MaxWords {
		return fmt.Errorf("follow-up exceeds %d words", policy.MaxWords)
	}

	lower := strings.ToLower(text)
	for _, marker := range []string{
		"good answer", "great answer", "excellent", "well said", "that's right",
		"that is right", "correct", "incorrect", "you should", "you need to",
	} {
		if strings.Contains(lower, marker) {
			return errors.New("follow-up contains assessment or correction")
		}
	}
	for _, marker := range []string{
		"don't you think", "do you not think", "wouldn't you agree", "would you not agree",
		"isn't it obvious", "is it not obvious", "surely ",
	} {
		if strings.Contains(lower, marker) {
			return errors.New("follow-up is leading")
		}
	}
	for _, term := range withheldLexis {
		term = strings.ToLower(strings.TrimSpace(term))
		if term != "" && strings.Contains(lower, term) {
			return errors.New("follow-up supplies withheld lexical resource")
		}
	}
	return nil
}

func countWords(text string) int {
	return len(strings.FieldsFunc(text, func(r rune) bool {
		return !unicode.IsLetter(r) && !unicode.IsNumber(r) && r != '\'' && r != '-'
	}))
}
