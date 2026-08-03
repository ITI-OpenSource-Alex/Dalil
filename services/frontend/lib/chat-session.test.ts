import { beforeEach, describe, expect, it } from "vitest";

import { getChatSessionId, startNewChatSession } from "./chat-session";

const STORAGE_KEY = "goa.chat.sessionId";

describe("chat session identity (GOA-038)", () => {
  beforeEach(() => {
    window.sessionStorage.clear();
  });

  it("creates and persists an id on first use", () => {
    const id = getChatSessionId();

    expect(id).toBeTruthy();
    expect(window.sessionStorage.getItem(STORAGE_KEY)).toBe(id);
  });

  it("returns the same id on reload, so a refresh continues the conversation", () => {
    const first = getChatSessionId();
    const second = getChatSessionId();

    expect(second).toBe(first);
  });

  it("is not the hardcoded id that made a second conversation impossible", () => {
    // The regression this whole phase exists for. With a constant id there is
    // no "next session", so cross-session memory cannot be demonstrated or
    // tested through the product at all.
    expect(getChatSessionId()).not.toBe("session-lina-123");
  });

  it("starts a genuinely different conversation on request", () => {
    const first = getChatSessionId();

    const second = startNewChatSession();

    expect(second).not.toBe(first);
    expect(getChatSessionId()).toBe(second);
  });

  it("gives different browser sessions different ids", () => {
    const first = getChatSessionId();
    window.sessionStorage.clear(); // what a new tab sees

    expect(getChatSessionId()).not.toBe(first);
  });
});
