/* -------------------------------------------------------------------------- */
/*                                   Types                                    */
/* -------------------------------------------------------------------------- */

export interface Opportunity {
  // See components/chat/chat-shell.tsx's Opportunity type for why this was added
  // (GOA-035): RAG's /match already returns it, this type just wasn't declaring it.
  programId: string;
  programName: string;
  university: string;
  country: string;
  deadline: string;
  confidence: number;
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

export class SSEParser {
  private buffer = "";

  /**
   * Feed raw decoded text into the parser.
   * Returns all COMPLETE SSE events found.
   */
  push(chunk: string): ChatEvent[] {
    this.buffer += chunk;

    const events: ChatEvent[] = [];

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
   * Useful when the stream closes.
   */
  flush(): ChatEvent[] {
    if (!this.buffer.trim()) {
      return [];
    }

    const event = this.parseEvent(this.buffer);

    this.buffer = "";

    return event ? [event] : [];
  }

  private parseEvent(rawEvent: string): ChatEvent | null {
    const lines = rawEvent.split("\n");

    let payload = "";

    for (const line of lines) {
      if (line.startsWith("data:")) {
        payload += line.substring(5).trim();
      }
    }

    if (!payload.length) {
      return null;
    }

    try {
      return JSON.parse(payload) as ChatEvent;
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

  const parser = new SSEParser();

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
