/**
 * The last line of defence between backend internals and the chat transcript.
 *
 * Orchestration's error path yields `Internal supervisor error: {str(e)}` for
 * any unhandled exception, and the chat shell rendered whatever arrived. A
 * Pydantic ValidationError, an asyncpg message or an httpx URL therefore
 * reached the user verbatim -- complete with service hostnames, internal ids
 * and the occasional stack fragment. Correlation ids are similar: useful in a
 * log, meaningless in a conversation.
 *
 * The server-side half of this is in services/orchestration/app/api/chat.py,
 * which no longer serialises the exception at all. This module exists because
 * the client should not depend on that being true of every future emitter:
 * anything that still looks like machine output is replaced here rather than
 * shown.
 */

/** What the user sees when a turn fails for a reason they cannot act on. */
export const GENERIC_ASSISTANT_ERROR =
  "Sorry — something went wrong while generating that response. Please try again.";

export const CONNECTION_ERROR =
  "I'm having trouble connecting right now. Please check your connection and try again.";

/**
 * Patterns whose presence means the string is diagnostic output rather than an
 * answer. Matching any one of them replaces the *entire* message: a sentence
 * that mixes prose with an exception type is still diagnostic output, and
 * excising the offending span would leave a mangled half-sentence that reads
 * as a bug either way.
 */
const INTERNAL_MARKERS: RegExp[] = [
  // Orchestration's own wrapper, and the shape of any raised Python error.
  /internal supervisor error/i,
  /\b\w*(?:Error|Exception)\b\s*[:(]/,
  /\bTraceback \(most recent call last\)/i,
  // Correlation / request / trace identifiers.
  /\b(?:correlation[_-]?id|request[_-]?id|trace[_-]?id|traceparent|span[_-]?id)\b/i,
  // Internal identity and tenancy fields. `tenant` is included even though
  // this deployment has no tenancy concept -- the point of a deny list is to
  // catch what the emitter gains later, not only what it emits today.
  /\b(?:tenant[_-]?id|tenant)\b/i,
  /\b(?:user[_-]?id|session[_-]?id|jti)\b\s*[:=]/i,
  // Service topology: Docker hostnames and internal ports.
  /\bhttps?:\/\/(?:localhost|127\.0\.0\.1|[a-z0-9-]+:\d{4,5})\b/i,
  /\b(?:rag|orchestration|writing|speaking|exam|gateway|user)-?service\b/i,
  // Raw JSON or dict dumps.
  /^\s*[[{][\s\S]*[\]}]\s*$/,
  /\bX-Internal-Api-Key\b/i,
];

/** True when `text` looks like backend diagnostics rather than an answer. */
export function looksInternal(text: string): boolean {
  if (!text) return false;
  return INTERNAL_MARKERS.some((pattern) => pattern.test(text));
}

/**
 * Returns text safe to render as an assistant reply.
 *
 * Empty input passes through unchanged so a stream that has not produced a
 * token yet is not replaced by an error the user has no reason to see.
 */
export function sanitizeAssistantText(
  text: string,
  fallback: string = GENERIC_ASSISTANT_ERROR,
): string {
  if (!text || !text.trim()) return text;
  return looksInternal(text) ? fallback : text;
}

/**
 * Turns an SSE `error` payload into something worth reading.
 *
 * The service-outage strings orchestration sends deliberately survive: "the
 * Writing evaluation service is currently offline" is written for a user, is
 * true, and tells them to come back later. Everything unrecognised collapses
 * to the generic message.
 */
export function sanitizeErrorMessage(error: unknown): string {
  if (typeof error !== "string" || !error.trim()) {
    return GENERIC_ASSISTANT_ERROR;
  }
  const trimmed = error.trim();
  if (looksInternal(trimmed)) return GENERIC_ASSISTANT_ERROR;

  // A bare machine token ("rate_limited", "subscription_required") is not a
  // sentence and should never be shown as one. Callers handle the ones that
  // carry meaning before reaching here.
  if (/^[a-z][a-z0-9_]*$/.test(trimmed)) return GENERIC_ASSISTANT_ERROR;

  return trimmed;
}
