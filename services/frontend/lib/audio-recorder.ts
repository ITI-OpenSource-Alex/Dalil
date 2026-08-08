export interface AudioRecorderOptions {
  onAudioChunk: (chunk: ArrayBuffer) => void;
}

/**
 * Formats we ask MediaRecorder for, best first.
 *
 * SPEAK-EVAL-002. This list exists because `new MediaRecorder(stream)` with no
 * mimeType picks whatever the browser prefers and never tells anyone — and the
 * backend then labelled the result `audio/pcm;rate=16000` and handed it to a
 * decoder that reads raw int16 samples. A compressed Opus container read as raw
 * samples is noise, so every browser-originated practice score was computed on
 * noise.
 *
 * Ordering rationale: Opus first because faster-whisper decodes it well at low
 * bitrate, WebM before Ogg because Chrome is the majority path, MP4/AAC last
 * because it is Safari's only option rather than a preference.
 */
const PREFERRED_MIME_TYPES = [
  "audio/webm;codecs=opus",
  "audio/webm",
  "audio/ogg;codecs=opus",
  "audio/ogg",
  "audio/mp4",
] as const;

export class UnsupportedRecordingError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "UnsupportedRecordingError";
  }
}

/**
 * Picks a format this browser can actually produce.
 *
 * Throws rather than falling back to an undeclared recording: the backend now
 * refuses audio whose encoding it does not know, and a clear error here beats a
 * refusal three services away.
 */
export function selectRecordingMimeType(): string {
  if (typeof MediaRecorder === "undefined") {
    throw new UnsupportedRecordingError(
      "This browser cannot record audio. Please use a recent version of Chrome, Firefox, Edge or Safari.",
    );
  }

  for (const mimeType of PREFERRED_MIME_TYPES) {
    // isTypeSupported is absent on some older WebKit builds, where MediaRecorder
    // exists but advertises nothing. Treating "no method" as "supports the first
    // candidate" would be a guess, so it is treated as unsupported.
    if (typeof MediaRecorder.isTypeSupported === "function" && MediaRecorder.isTypeSupported(mimeType)) {
      return mimeType;
    }
  }

  throw new UnsupportedRecordingError(
    "This browser does not support any audio format we can transcribe. Please try Chrome, Firefox or Edge.",
  );
}

export class AudioRecorder {
  private mediaRecorder: MediaRecorder | null = null;
  private stream: MediaStream | null = null;
  private mimeType: string | null = null;

  constructor(private options: AudioRecorderOptions) {}

  async start() {
    // Chosen before getUserMedia so an unsupported browser fails without ever
    // prompting for the microphone.
    const mimeType = selectRecordingMimeType();

    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: true,
    });

    this.mediaRecorder = new MediaRecorder(this.stream, { mimeType });

    // What the browser actually chose. MediaRecorder is permitted to normalise
    // the request (dropping a codecs parameter, say), and the declared format
    // must describe the bytes rather than the request.
    this.mimeType = this.mediaRecorder.mimeType || mimeType;

    this.mediaRecorder.ondataavailable = async (event) => {
      if (!event.data.size) return;

      const buffer = await event.data.arrayBuffer();

      this.options.onAudioChunk(buffer);
    };

    // Send chunks every 250ms.
    //
    // Only the FIRST chunk carries the container header; the rest are fragments
    // that no decoder can read alone. The Go service concatenates the whole
    // utterance before transcribing, which is why this works — but it means a
    // suffix of the stream is never independently decodable. Do not transcribe a
    // partial buffer that does not start at the beginning of the recording.
    this.mediaRecorder.start(250);
  }

  /**
   * The MIME type of the bytes this recorder is emitting, or null before
   * start() resolves. Sent in session_init so the backend can label the upload
   * honestly instead of asserting PCM.
   */
  getMimeType(): string | null {
    return this.mimeType;
  }

  stop() {
    this.mediaRecorder?.stop();

    this.stream?.getTracks().forEach((track) => track.stop());

    this.mediaRecorder = null;
    this.stream = null;
    this.mimeType = null;
  }

  /**
   * Exposes the live MediaStream so other consumers (e.g. a waveform
   * visualizer) can tap the same microphone stream instead of requesting
   * getUserMedia a second time. Returns null before start() resolves or
   * after stop() has released the stream.
   */
  getStream(): MediaStream | null {
    return this.stream;
  }
}
