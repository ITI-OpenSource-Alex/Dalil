/**
 * Chat session identity (GOA-038).
 *
 * The session id used to be the constant string "session-lina-123". Every
 * browser, every tab and every reload shared one conversation, which meant
 * there was no such thing as starting a new one — and "the assistant remembers
 * you across sessions" cannot be demonstrated, or even tested, in a product
 * where a second session is unreachable.
 *
 * sessionStorage rather than localStorage: a reload continues the conversation
 * you were having, a new tab starts a fresh one. That matches what "session"
 * means to the person using it, and it gives the long-term memory feature
 * something to be visible against.
 *
 * This does not touch the hardcoded profile header or the fixed exam bands
 * (BUG-047) — those belong to GOA-035.
 */

const STORAGE_KEY = "goa.chat.sessionId";

function generateId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  // Older Safari and any non-secure-context origin have no randomUUID. The id
  // only has to be unique per browser session, not unguessable — the server
  // trusts the JWT for identity, never this.
  return `s-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

/** The current session id, creating and persisting one on first use. */
export function getChatSessionId(): string {
  if (typeof window === "undefined") return "";

  const existing = window.sessionStorage.getItem(STORAGE_KEY);
  if (existing) return existing;

  const fresh = generateId();
  window.sessionStorage.setItem(STORAGE_KEY, fresh);
  return fresh;
}

/** Abandon the current conversation and start a new one. Returns the new id. */
export function startNewChatSession(): string {
  const fresh = generateId();
  if (typeof window !== "undefined") {
    window.sessionStorage.setItem(STORAGE_KEY, fresh);
  }
  return fresh;
}
