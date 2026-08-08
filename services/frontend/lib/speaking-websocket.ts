export type SocketSpeakingState =
  | "idle"
  | "connecting"
  | "connected"
  | "recording"
  | "processing"
  | "done"
  | "error";

/**
 * One IELTS criterion, delivered the moment its evaluation agent finishes
 * (GOA-032). Four of these arrive before the aggregate below, so the UI can
 * show real feedback while the remaining agents are still running.
 */
export interface SpeakingCriterion {
  criterion: string;
  /** Absent when the criterion timed out — never 0, which would render as a
   *  real band of zero for an agent that never scored. */
  band?: number;
  feedback: string;
  examples?: string[];
  timed_out: boolean;
  elapsed_ms: number;
}

export interface SpeakingEvaluation {
  /**
   * Absent when fewer than 3 of the 4 criteria completed. A band averaged from
   * one or two surviving agents describes which agents survived, not the
   * candidate (BUG-040), so the backend omits the key entirely rather than
   * sending a number the UI would have no way to distrust.
   */
  overall_band?: number;
  completed_count: number;
  dimensions: Record<string, unknown>;
  overall_feedback: string;
  partial?: boolean;
  status?: string;
}

/**
 * Version of the speaking WebSocket protocol this client speaks.
 *
 * v1 was: session_init {userId, questionPrompt, questionType}, binary frames,
 * and an inactivity timer on the server deciding the utterance had ended.
 *
 * v2 (SPEAK-EVAL-002) adds the recorded audio format to session_init and an
 * explicit `audio_end` control frame. The format matters because the server used
 * to assert `audio/pcm;rate=16000` regardless of what the browser recorded; the
 * end frame matters because a 1.5s silence timer cannot tell a finished
 * recording from a stalled client.
 */
export const SPEAKING_PROTOCOL_VERSION = 2;

interface SpeakingSessionOptions {
  wsUrl: string;
  userId: string;
  questionPrompt: string;
  questionType: string;
  /**
   * MIME type of the audio frames this session will send, from
   * AudioRecorder.getMimeType(). Required: the server refuses a session that
   * does not declare one rather than guessing at the encoding.
   */
  audioFormat: string;

  onStateChange?: (state: SocketSpeakingState) => void;
  /** Fires up to four times per utterance, as each agent completes. */
  onCriterion?: (criterion: SpeakingCriterion) => void;
  onEvaluation?: (evaluation: SpeakingEvaluation) => void;
  onError?: (message: string) => void;
  onTtsChunk?: (audio: ArrayBuffer) => void;
  onTranscript?: (text: string, isFinal: boolean) => void;
}

export class SpeakingWebSocket {
  private socket: WebSocket | null = null;

  /**
   * Chunks recorded before the socket finished connecting.
   *
   * The recorder now starts before the socket, because session_init has to
   * declare the format. That means the first chunks can arrive while the
   * handshake is still in flight — and dropping them is not survivable: only
   * the FIRST chunk carries the container header, so losing it makes the whole
   * utterance undecodable rather than merely shorter.
   *
   * Bounded, because an unbounded queue against a socket that never opens is a
   * memory leak. At 250ms per chunk this holds ~10 seconds, far longer than any
   * successful handshake; past that the session has failed anyway.
   */
  private pendingAudio: (ArrayBuffer | Blob)[] = [];
  private static readonly MAX_PENDING_CHUNKS = 40;

  constructor(private options: SpeakingSessionOptions) {}

  connect() {
    this.options.onStateChange?.("connecting");

    this.socket = new WebSocket(this.options.wsUrl);
    this.socket.binaryType = "arraybuffer";

    this.socket.onopen = () => {
      this.options.onStateChange?.("connected");

      this.socket?.send(
        JSON.stringify({
          type: "session_init",
          protocolVersion: SPEAKING_PROTOCOL_VERSION,
          userId: this.options.userId,
          questionPrompt: this.options.questionPrompt,
          questionType: this.options.questionType,
          audioFormat: this.options.audioFormat,
        }),
      );

      // Flush anything recorded during the handshake, in order and immediately
      // after session_init, so the server sees a contiguous stream starting at
      // the container header.
      for (const chunk of this.pendingAudio) {
        this.socket?.send(chunk);
      }
      this.pendingAudio = [];

      this.options.onStateChange?.("recording");
    };

    this.socket.onmessage = async (event) => {
      // Binary frames are TTS audio from the local Piper sidecar. Every control
      // and result frame is text, including tts_unavailable — the Gateway proxy
      // preserves the opcode end to end, so this check is authoritative.
      if (event.data instanceof Blob) {
        const buffer = await event.data.arrayBuffer();
        this.options.onTtsChunk?.(buffer);
        return;
      }
      if (event.data instanceof ArrayBuffer) {
        this.options.onTtsChunk?.(event.data);
        return;
      }

      const data = JSON.parse(event.data);

      switch (data.type) {
        case "transcript":
          this.options.onTranscript?.(data.text, data.isFinal ?? false);
          break;

        case "criterion":
          this.options.onCriterion?.(data as SpeakingCriterion);
          break;

        case "evaluation":
          this.options.onEvaluation?.(data as SpeakingEvaluation);
          break;

        case "tts_unavailable":
          // Not an error the user needs to see: the written evaluation has
          // already arrived and is the substance. Only the voiceover is missing.
          this.options.onStateChange?.("done");
          break;

        case "error":
          this.options.onError?.(data.message);
          break;
      }
    };

    this.socket.onerror = () => {
      this.options.onStateChange?.("error");
      this.options.onError?.("WebSocket connection failed.");
    };

    this.socket.onclose = (event) => {
      // 1008 is a policy decision relayed intact through the Gateway proxy —
      // today that means the daily speaking budget (GOA-034). Surfacing the
      // reason is the difference between an explanation and a dead spinner.
      if (event.code === 1008 && event.reason) {
        this.options.onError?.(event.reason);
        this.options.onStateChange?.("error");
      }
    };
  }

  /**
   * Sends one audio chunk to the backend, in the format declared at
   * session_init. Only the first chunk carries the container header, so the
   * server must concatenate the whole utterance before decoding.
   */
  sendAudio(chunk: ArrayBuffer | Blob) {
    if (this.socket?.readyState === WebSocket.OPEN) {
      this.socket.send(chunk);
      return;
    }

    // Still connecting: queue rather than drop. See pendingAudio.
    if (this.socket?.readyState === WebSocket.CONNECTING) {
      if (this.pendingAudio.length < SpeakingWebSocket.MAX_PENDING_CHUNKS) {
        this.pendingAudio.push(chunk);
      }
    }
    // CLOSING/CLOSED or no socket: the session is over, nothing to preserve.
  }

  /**
   * User finished speaking.
   *
   * Sends an explicit `audio_end` so the server transcribes immediately instead
   * of waiting out a 1.5-second silence timer. That timer stays on the server as
   * a fallback for a client that vanishes mid-recording, but it is no longer how
   * a normal recording completes — it could not distinguish "finished" from
   * "stalled", and it charged every user 1.5 seconds of latency to find out.
   *
   * The server treats end-of-audio idempotently, so a duplicate frame or an
   * `audio_end` racing the fallback timer cannot transcribe the same utterance
   * twice.
   */
  finishRecording() {
    this.options.onStateChange?.("processing");

    if (this.socket?.readyState === WebSocket.OPEN) {
      this.socket.send(JSON.stringify({ type: "audio_end" }));
    }
  }

  close() {
    this.socket?.close();
    this.socket = null;
    this.pendingAudio = [];
    this.options.onStateChange?.("idle");
  }
}
