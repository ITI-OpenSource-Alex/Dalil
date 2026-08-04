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

interface SpeakingSessionOptions {
  wsUrl: string;
  userId: string;
  questionPrompt: string;
  questionType: string;

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
          userId: this.options.userId,
          questionPrompt: this.options.questionPrompt,
          questionType: this.options.questionType,
        }),
      );

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
   * Sends one audio chunk to the backend.
   * Backend expects binary PCM frames.
   */
  sendAudio(chunk: ArrayBuffer | Blob) {
    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
      return;
    }

    this.socket.send(chunk);
  }

  /**
   * User finished speaking.
   * Stop recording but leave the socket open until
   * the backend returns the evaluation.
   */
  finishRecording() {
    this.options.onStateChange?.("processing");
  }

  close() {
    this.socket?.close();
    this.socket = null;
    this.options.onStateChange?.("idle");
  }
}
