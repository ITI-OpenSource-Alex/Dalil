package agents

import (
	"fmt"
	"strings"
)

// GOA-133. Acoustic features, measured from the audio, for the two criteria that
// are defined over acoustics and were being scored from text.
//
// Fluency and Coherence assesses "rate of speech (flow, pauses, hesitation,
// self-correction)". Pronunciation assesses intelligibility. Neither is
// recoverable from a transcript: measured on two renderings of one script,
// 18.87s and 33.67s, the speech sidecar returned byte-identical text. The
// information was destroyed before any agent saw it, and no prompt wording could
// have recovered it.
//
// faster-whisper computed all of this on every call already; the sidecar
// discarded it on the line after it was produced.

// Word is one token with its timing and the model's confidence in it, as
// returned by the speech sidecar.
type Word struct {
	Word        string  `json:"word"`
	Start       float64 `json:"start"`
	End         float64 `json:"end"`
	Probability float64 `json:"probability"`
}

// Thresholds. Named, because a bare 0.3 in an expression is a magic number that
// nobody can later argue with.
const (
	// pauseThresholdS is the gap above which silence reads as a pause rather than
	// the ordinary gap between words. Below roughly 0.25s a listener does not
	// perceive a break at all.
	pauseThresholdS = 0.3

	// longPauseThresholdS marks a hesitation a listener notices and an examiner
	// would mark down. Distinguished from pauseThresholdS because "many short
	// gaps" and "a few long silences" are different fluency profiles that would
	// otherwise produce the same count.
	longPauseThresholdS = 1.0

	// lowConfidenceThreshold is where Whisper's per-word probability stops being
	// a vote of confidence. It is NOT a pronunciation score -- it is the model's
	// certainty about the token -- but it is the only intelligibility signal
	// available without forced alignment, and unlike the previous approach it is
	// a measurement rather than an inference from spelling.
	lowConfidenceThreshold = 0.5
)

// ProsodyFeatures is what the Fluency and Pronunciation agents actually get to
// reason about. Every field is measured; none is inferred from the transcript.
type ProsodyFeatures struct {
	SpeechDurationS float64
	WordCount       int

	WordsPerMinute float64
	// ArticulationRate is words per minute of SPEAKING time, with pauses removed.
	// Reported alongside WordsPerMinute because the two separate "speaks slowly"
	// from "speaks normally but pauses a lot" -- different criteria problems with
	// different advice, indistinguishable from WPM alone.
	ArticulationRate float64

	PauseCount     int
	LongPauseCount int
	LongestPauseS  float64
	PauseRatio     float64

	MeanWordConfidence     float64
	LowConfidenceWordRatio float64
}

// ComputeProsody derives the features from the sidecar's word timings.
//
// ok is false when there is nothing to measure. Callers must omit the feature
// block entirely in that case rather than rendering zeros: a block reading
// "0 words per minute, 0 pauses" describes a candidate who said nothing, which
// is a worse lie than saying nothing at all. This is the BUG-055 shape applied
// to prosody.
func ComputeProsody(words []Word, durationS float64) (ProsodyFeatures, bool) {
	if len(words) == 0 || durationS <= 0 {
		return ProsodyFeatures{}, false
	}

	f := ProsodyFeatures{
		SpeechDurationS: durationS,
		WordCount:       len(words),
	}

	var totalPauseS float64
	var confidenceSum float64
	var lowConfidence int

	for i, w := range words {
		confidenceSum += w.Probability
		if w.Probability < lowConfidenceThreshold {
			lowConfidence++
		}
		if i == 0 {
			continue
		}
		gap := w.Start - words[i-1].End
		if gap <= 0 {
			continue
		}
		if gap >= pauseThresholdS {
			f.PauseCount++
			totalPauseS += gap
			if gap >= longPauseThresholdS {
				f.LongPauseCount++
			}
		}
		if gap > f.LongestPauseS {
			f.LongestPauseS = gap
		}
	}

	f.WordsPerMinute = float64(len(words)) / (durationS / 60.0)

	// Speaking time excludes the pauses. Guarded: a clip that is almost entirely
	// silence would otherwise divide by ~0 and report an articulation rate in the
	// thousands.
	speakingS := durationS - totalPauseS
	if speakingS > 0.5 {
		f.ArticulationRate = float64(len(words)) / (speakingS / 60.0)
	} else {
		f.ArticulationRate = f.WordsPerMinute
	}

	f.PauseRatio = totalPauseS / durationS
	f.MeanWordConfidence = confidenceSum / float64(len(words))
	f.LowConfidenceWordRatio = float64(lowConfidence) / float64(len(words))

	return f, true
}

// Render formats the features for a prompt.
//
// Deliberately NOT wrapped in wrap_untrusted/its Go equivalent: these are our own
// computed numbers, not user-supplied content, and fencing them would tell the
// model to distrust the one part of the prompt it should trust most. The
// transcript stays fenced.
func (f ProsodyFeatures) Render() string {
	var b strings.Builder
	b.WriteString("MEASURED SPEECH FEATURES (computed from the audio, not inferred from the text):\n")
	fmt.Fprintf(&b, "  Speech duration: %.1fs across %d words\n", f.SpeechDurationS, f.WordCount)
	fmt.Fprintf(&b,
		"  Speech rate: %.0f words per minute (articulation rate excluding pauses: %.0f wpm)\n",
		f.WordsPerMinute, f.ArticulationRate,
	)
	fmt.Fprintf(&b,
		"  Pauses >=%.1fs: %d  ·  >=%.1fs: %d  ·  longest: %.1fs  ·  %.0f%% of total time spent paused\n",
		pauseThresholdS, f.PauseCount, longPauseThresholdS, f.LongPauseCount,
		f.LongestPauseS, f.PauseRatio*100,
	)
	fmt.Fprintf(&b,
		"  Speech recognition confidence: mean %.2f, with %.0f%% of words below %.1f\n",
		f.MeanWordConfidence, f.LowConfidenceWordRatio*100, lowConfidenceThreshold,
	)
	return b.String()
}
