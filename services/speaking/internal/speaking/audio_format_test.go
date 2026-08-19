package speaking

import (
	"errors"
	"strings"
	"testing"
)

// SPEAK-EVAL-002 — format validation at session_init.

func TestNormalizeAudioFormatAcceptsWhatBrowsersSend(t *testing.T) {
	for _, tc := range []struct {
		declared string
		want     string
	}{
		// The exact strings MediaRecorder.mimeType reports.
		{"audio/webm;codecs=opus", "audio/webm"},
		{"audio/webm", "audio/webm"},
		{"audio/ogg;codecs=opus", "audio/ogg"},
		{"audio/ogg", "audio/ogg"},
		{"audio/mp4", "audio/mp4"},
		// Non-browser clients: the integration suite and the k6 load test.
		{"audio/pcm;rate=16000", "audio/pcm"},
		{"audio/pcm", "audio/pcm"},
		// Case and whitespace are the client's, not ours.
		{"AUDIO/WEBM;CODECS=OPUS", "audio/webm"},
		{"  audio/webm  ", "audio/webm"},
	} {
		t.Run(tc.declared, func(t *testing.T) {
			got, err := normalizeAudioFormat(tc.declared)
			if err != nil {
				t.Fatalf("rejected %q: %v", tc.declared, err)
			}
			if got != tc.want {
				t.Errorf("normalizeAudioFormat(%q) = %q, want %q", tc.declared, got, tc.want)
			}
		})
	}
}

func TestNormalizeAudioFormatRejections(t *testing.T) {
	for _, tc := range []struct {
		name     string
		declared string
		wantErr  error
	}{
		{"empty", "", errAudioFormatMissing},
		{"whitespace only", "   ", errAudioFormatMissing},
		{"not a media type", "webm", errAudioFormatUnsupported},
		{"malformed parameters", "audio/webm; codecs", errAudioFormatMalformed},
		{"video container", "video/mp4", errAudioFormatUnsupported},
		{"unsupported codec container", "audio/flac", errAudioFormatUnsupported},
	} {
		t.Run(tc.name, func(t *testing.T) {
			_, err := normalizeAudioFormat(tc.declared)
			if err == nil {
				t.Fatalf("accepted %q", tc.declared)
			}
			if !errors.Is(err, tc.wantErr) {
				t.Errorf("error = %v, want %v", err, tc.wantErr)
			}
		})
	}
}

// TestMissingFormatErrorTellsTheUserWhatToDo — a v1 browser tab connecting after
// deploy gets this message. "Invalid payload" would leave them stuck.
func TestMissingFormatErrorIsActionable(t *testing.T) {
	_, err := normalizeAudioFormat("")
	if err == nil {
		t.Fatal("expected an error")
	}
	if !strings.Contains(strings.ToLower(err.Error()), "refresh") {
		t.Errorf("error does not tell the user how to recover: %q", err)
	}
}

func TestUnsupportedFormatErrorListsWhatIsSupported(t *testing.T) {
	_, err := normalizeAudioFormat("audio/flac")
	if err == nil {
		t.Fatal("expected an error")
	}
	for _, want := range []string{"audio/webm", "audio/ogg", "audio/mp4"} {
		if !strings.Contains(err.Error(), want) {
			t.Errorf("error does not mention %q: %q", want, err)
		}
	}
}

// TestOnlyRawPCMClaimsByteDerivableDuration — the guard on the second defect.
//
// pcmDurationMs infers seconds from byte count, which is only meaningful for
// headerless PCM. Marking a compressed format isRawPCM would silently restore
// the transcription_ratio bug.
func TestOnlyRawPCMClaimsByteDerivableDuration(t *testing.T) {
	for mediaType, format := range supportedAudioFormats {
		if format.isRawPCM && mediaType != "audio/pcm" {
			t.Errorf(
				"%s is marked isRawPCM. Duration would be inferred from byte count, "+
					"but compressed audio has no fixed bytes-per-second -- measured on "+
					"the test fixtures, Opus is ~9.5x smaller than the PCM of the same "+
					"6 seconds.",
				mediaType,
			)
		}
	}
	if pcm, ok := supportedAudioFormats["audio/pcm"]; !ok || !pcm.isRawPCM {
		t.Error("audio/pcm must be marked isRawPCM")
	}
}

// TestNoFormatUploadsAsPCMByAccident — the registry-level version of the defect.
func TestOnlyPCMUploadsAsPCM(t *testing.T) {
	for mediaType, format := range supportedAudioFormats {
		declaresPCM := strings.Contains(format.uploadContentType, "audio/pcm")
		if declaresPCM && mediaType != "audio/pcm" {
			t.Errorf(
				"%s uploads as %q. The sidecar frombuffers anything matching "+
					"audio/pcm into int16 samples, so this would decode as noise.",
				mediaType, format.uploadContentType,
			)
		}
	}
}

func TestEveryFormatHasADistinctExtension(t *testing.T) {
	seen := map[string]string{}
	for mediaType, format := range supportedAudioFormats {
		if format.extension == "" || !strings.HasPrefix(format.extension, ".") {
			t.Errorf("%s has an invalid extension %q", mediaType, format.extension)
		}
		if prev, dup := seen[format.extension]; dup {
			t.Errorf("%s and %s share extension %q", prev, mediaType, format.extension)
		}
		seen[format.extension] = mediaType
	}
}

func TestFormatRejectReasonIsBounded(t *testing.T) {
	// Prometheus labels must come from a fixed set; the declared format is
	// client-controlled and must never become one.
	allowed := map[string]bool{"missing": true, "unsupported": true, "malformed": true, "unknown": true}
	for _, declared := range []string{"", "audio/flac", "audio/webm; codecs", "nonsense"} {
		_, err := normalizeAudioFormat(declared)
		if err == nil {
			continue
		}
		reason := formatRejectReason(err)
		if !allowed[reason] {
			t.Errorf("formatRejectReason(%q) = %q, which is outside the bounded label set", declared, reason)
		}
	}
	if got := formatRejectReason(errors.New("something else")); got != "unknown" {
		t.Errorf("unclassified error mapped to %q, want \"unknown\"", got)
	}
}
