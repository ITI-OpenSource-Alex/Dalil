/* -------------------------------------------------------------------------- */
/*                                   Types                                    */
/* -------------------------------------------------------------------------- */

export interface Opportunity {
  // See components/chat/chat-shell.tsx's Opportunity type for why this was added
  // (GOA-035): RAG's /match already returns it, this type just wasn't declaring it.
  // `result.score` (0-100) is the real field name/scale -- see that type's
  // comment for why this isn't a flat `confidence: number`.
  programId: string;
  programName: string;
  university: string;
  country: string;
  // Nullable: the column is optional in program_requirements and RAG
  // passes None straight through, which the UI rendered as "Deadline: null".
  deadline: string | null;
  result: {
    score: number;
    blocked_by: string | null;
  };
}

export interface EvaluationDimension {
  name: string;
  score: number;
}

export interface SpeakingEvaluation {
  overallBand: number;
  dimensions: EvaluationDimension[];
  feedback: string;
}

export interface MetadataEvent {
  type: "metadata";
  intent: string;
  confidence?: number;
}

export interface StatusEvent {
  type: "status";
  stage: "connecting" | "routing" | "retrieving" | "generating";
  message: string;
}

export interface TokenEvent {
  type: "token";
  content: string;
}

export interface SourcesEvent {
  type: "sources";
  sources: string[];
}

export interface WritingUrlEvent {
  type: "writing_url";
  essayId: string;
  sseUrl: string;
}

export interface SpeakingUrlEvent {
  type: "speaking_url";
  wsUrl: string;
}

export interface MatchResultsEvent {
  type: "match_results";
  programs: Opportunity[];
}

export interface ErrorEvent {
  type: "error";
  error: string;
}

export type ChatEvent =
  | StatusEvent
  | MetadataEvent
  | TokenEvent
  | SourcesEvent
  | WritingUrlEvent
  | SpeakingUrlEvent
  | MatchResultsEvent
  | ErrorEvent;

/* -------------------------------------------------------------------------- */
/*                               SSE Event Parser                             */
/* -------------------------------------------------------------------------- */

/** One raw SSE frame, split into its `event:` name (if any) and its parsed
 *  JSON `data:` payload -- the two pieces every caller's own event shape is
 *  built from. */
export interface RawSSEEvent {
  /** The `event:` line's value, e.g. "section" or "complete". Undefined for
   *  a frame with no event line (orchestration and the writing service's
   *  older endpoints send data-only frames with the event's `type` embedded
   *  in the JSON payload instead). */
  eventName?: string;
  data: unknown;
}

/**
 * Generic SSE frame reassembly: buffers decoded text, splits it on blank-line
 * boundaries into complete frames, and JSON-parses each frame's `data:`
 * payload. What differs between SSE producers in this app is only how a raw
 * frame becomes *that caller's* event type -- chat's orchestration and the
 * writing service both embed a `type` field in the JSON body itself, while
 * the CV review endpoint puts it in the `event:` line instead. That mapping
 * is the `parse` callback; everything else (buffering, the CRLF fix below,
 * the trailing-frame flush) is shared, where it used to be reimplemented
 * three times across chat-stream.ts, writing-stream.ts and cv-api.ts -- once
 * including the trailing-frame bug, once fixing it, and once fixing it again
 * independently.
 */
export class SSEParser<T> {
  private buffer = "";

  constructor(private readonly parse: (event: RawSSEEvent) => T | null) {}

  /**
   * Feed raw decoded text into the parser.
   * Returns all COMPLETE SSE events found.
   */
  push(chunk: string): T[] {
    // Orchestration's EventSourceResponse (sse-starlette) frames events with
    // CRLF ("\r\n"), not the bare LF this parser's "\n\n" separator search
    // expects. Left unnormalized, indexOf("\n\n") never matches, every event
    // silently accumulates in the buffer, and flush() eventually concatenates
    // multiple JSON payloads into one invalid blob that fails JSON.parse --
    // the assistant's reply never renders at all, with no visible error.
    // Harmless no-op for producers (writing, CV review) that only ever send
    // bare LF.
    this.buffer += chunk.replace(/\r\n/g, "\n");

    const events: T[] = [];

    while (true) {
      const separatorIndex = this.buffer.indexOf("\n\n");

      if (separatorIndex === -1) {
        break;
      }

      const rawEvent = this.buffer.slice(0, separatorIndex);
      this.buffer = this.buffer.slice(separatorIndex + 2);

      const event = this.parseEvent(rawEvent);

      if (event) {
        events.push(event);
      }
    }

    return events;
  }

  /**
   * Flush any remaining buffered data.
   *
   * The stream's final frame has no reason to be followed by a trailing
   * "\n\n" -- the connection just closes right after it. Without this, that
   * last frame sits in the buffer waiting for a separator that will never
   * arrive and is silently dropped once the read loop exits on `done`.
   */
  flush(): T[] {
    if (!this.buffer.trim()) {
      return [];
    }

    const event = this.parseEvent(this.buffer);

    this.buffer = "";

    return event ? [event] : [];
  }

  private parseEvent(rawEvent: string): T | null {
    const lines = rawEvent.split("\n");

    let eventName: string | undefined;
    let payload = "";

    for (const line of lines) {
      if (line.startsWith("event:")) {
        eventName = line.substring(6).trim();
      } else if (line.startsWith("data:")) {
        payload += line.substring(5).trim();
      }
    }

    if (!payload.length) {
      return null;
    }

    try {
      const data = JSON.parse(payload) as unknown;
      return this.parse({ eventName, data });
    } catch (err) {
      console.warn("Failed to parse SSE event:", payload);
      return null;
    }
  }
}

/* -------------------------------------------------------------------------- */
/*                           Stream Reader Helper                             */
/* -------------------------------------------------------------------------- */

export async function streamChatResponse(
  response: Response,
  onEvent: (event: ChatEvent) => void,
) {
  if (!response.body) {
    throw new Error("Response body is empty.");
  }

  // Orchestration's frames embed their own `type` field in the JSON body --
  // the `event:` line, if present at all, is not what discriminates them.
  const parser = new SSEParser<ChatEvent>(({ data }) => data as ChatEvent);

  const reader = response.body.getReader();

  const decoder = new TextDecoder();

  while (true) {
    const { value, done } = await reader.read();

    if (done) {
      break;
    }

    const chunk = decoder.decode(value, {
      stream: true,
    });

    const events = parser.push(chunk);

    events.forEach(onEvent);
  }

  parser.flush().forEach(onEvent);
}
