package speaking

import (
	"errors"
	"fmt"
	"mime"
	"strings"
)

// SPEAK-EVAL-002 — the audio format contract.
//
// The browser records with MediaRecorder, which emits an encoded container:
// WebM/Opus on Chrome, Ogg/Opus on Firefox, MP4/AAC on Safari. This service used
// to forward those bytes to the speech sidecar labelled
// "audio/pcm;rate=16000", and the sidecar decodes anything matching audio/pcm
// with np.frombuffer(dtype=int16). A compressed container read as raw samples is
// noise, so every browser-originated score was computed on noise.
//
// The defect survived because the Go integration tests and the k6 load test
// construct real PCM -- they validated a contract no browser produces.
//
// This file is the one place that knows which encodings exist and what each one
// is called on the wire. Adding a format means adding it here, not scattering a
// new string through the upload path.

// audioFormat describes one encoding this service is prepared to accept.
type audioFormat struct {
	// mediaType is the canonical MIME type, parameters stripped.
	mediaType string
	// uploadContentType is what the sidecar is told. Parameters that matter to
	// the decoder are kept: raw PCM is meaningless without its sample rate.
	uploadContentType string
	// extension is used for the upload filename. Decoders sniff content rather
	// than trusting it, but the filename is the first thing a human reads when
	// diagnosing this path, and "audio.pcm" holding Opus is how the original
	// defect hid in plain sight.
	extension string
	// isRawPCM marks the one format whose duration can be derived from its byte
	// count. Everything else is compressed, so bytes say nothing about seconds.
	isRawPCM bool
}

// supportedAudioFormats is keyed by canonical media type.
//
// Ogg and WebM both appear because Firefox and Chrome disagree, and MP4 because
// it is Safari's only option. faster-whisper decodes all three through ffmpeg,
// which services/speech already installs.
var supportedAudioFormats = map[string]audioFormat{
	"audio/webm": {
		mediaType:         "audio/webm",
		uploadContentType: "audio/webm",
		extension:         ".webm",
	},
	"audio/ogg": {
		mediaType:         "audio/ogg",
		uploadContentType: "audio/ogg",
		extension:         ".ogg",
	},
	"audio/mp4": {
		mediaType:         "audio/mp4",
		uploadContentType: "audio/mp4",
		extension:         ".m4a",
	},
	// Retained for the integration and load tests, and for any non-browser
	// client that genuinely streams raw samples. The sample rate is part of the
	// declaration because the sidecar cannot infer it from headerless bytes.
	"audio/pcm": {
		mediaType:         "audio/pcm",
		uploadContentType: "audio/pcm;rate=16000",
		extension:         ".pcm",
		isRawPCM:          true,
	},
}

var (
	errAudioFormatMissing     = errors.New("audio format missing")
	errAudioFormatUnsupported = errors.New("audio format unsupported")
	errAudioFormatMalformed   = errors.New("audio format malformed")
)

// normalizeAudioFormat validates a client-declared MIME type and returns the
// canonical media type used to look the format up.
//
// Codec parameters are accepted and discarded: "audio/webm;codecs=opus" and
// "audio/webm" decode identically through ffmpeg, and rejecting the former would
// refuse the exact string Chrome reports.
func normalizeAudioFormat(declared string) (string, error) {
	trimmed := strings.TrimSpace(declared)
	if trimmed == "" {
		return "", fmt.Errorf(
			"%w: this session did not declare what audio format it is recording. "+
				"Please refresh the page to load the current version",
			errAudioFormatMissing,
		)
	}

	mediaType, _, err := mime.ParseMediaType(trimmed)
	if err != nil {
		return "", fmt.Errorf(
			"%w: %q is not a valid media type",
			errAudioFormatMalformed, trimmed,
		)
	}

	mediaType = strings.ToLower(mediaType)
	if _, ok := supportedAudioFormats[mediaType]; !ok {
		return "", fmt.Errorf(
			"%w: this service cannot transcribe %q. Supported formats: %s",
			errAudioFormatUnsupported, mediaType, strings.Join(supportedFormatNames(), ", "),
		)
	}

	return mediaType, nil
}

func supportedFormatNames() []string {
	// Fixed order so the error message is stable across runs; ranging a map is
	// randomised in Go and a message that reshuffles itself is harder to search
	// for in a bug report.
	return []string{"audio/webm", "audio/ogg", "audio/mp4", "audio/pcm"}
}

// lookupAudioFormat returns the upload parameters for a normalized media type.
// The bool is false when the format is unknown, which callers must treat as a
// refusal to transcribe rather than a reason to fall back.
func lookupAudioFormat(mediaType string) (audioFormat, bool) {
	f, ok := supportedAudioFormats[mediaType]
	return f, ok
}

// formatRejectReason maps a validation error to a bounded metric label. The
// declared format itself is never used as a label -- it is client-controlled and
// would blow up Prometheus cardinality.
func formatRejectReason(err error) string {
	switch {
	case errors.Is(err, errAudioFormatMissing):
		return "missing"
	case errors.Is(err, errAudioFormatUnsupported):
		return "unsupported"
	case errors.Is(err, errAudioFormatMalformed):
		return "malformed"
	default:
		return "unknown"
	}
}
