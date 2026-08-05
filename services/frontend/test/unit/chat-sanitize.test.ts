import { describe, expect, it } from "vitest";
import {
  GENERIC_ASSISTANT_ERROR,
  looksInternal,
  sanitizeAssistantText,
  sanitizeErrorMessage,
} from "@/lib/chat-sanitize";
import { presentableSources } from "@/components/chat/sources-footnote";

describe("looksInternal", () => {
  it.each([
    // The exact string orchestration used to emit.
    "Internal supervisor error: 1 validation error for ChatStreamEvent",
    "ValidationError: field required",
    "httpx.ConnectError: [Errno 111] Connection refused",
    "Traceback (most recent call last):",
    "correlation_id: 7f3c2b1a-...",
    "trace_id=abcdef",
    "tenant_id: acme-prod",
    "user_id: 8c1f...",
    "Failed to reach http://rag:8001/query",
    "rag-service returned 500",
    '{"answer": null, "reason": "low_confidence"}',
  ])("flags %s", (text) => {
    expect(looksInternal(text)).toBe(true);
  });

  it.each([
    "You'll need an IELTS band of 6.5 for that programme.",
    "I'm sorry, but the Writing evaluation service is currently offline. Please try again later.",
    "The application deadline is 15 October 2026.",
    "Your GPA of 3.4 clears the minimum for four of these programmes.",
  ])("leaves a genuine answer alone: %s", (text) => {
    expect(looksInternal(text)).toBe(false);
  });
});

describe("sanitizeAssistantText", () => {
  it("replaces diagnostic output with the generic message", () => {
    expect(
      sanitizeAssistantText("Internal supervisor error: KeyError('answer')"),
    ).toBe(GENERIC_ASSISTANT_ERROR);
  });

  it("passes a real answer through unchanged", () => {
    const answer = "TU Berlin's MSc Computer Science asks for 90 ECTS.";
    expect(sanitizeAssistantText(answer)).toBe(answer);
  });

  it("leaves an empty stream empty rather than erroring on it", () => {
    // A bubble that has not received its first token yet is not a failure.
    expect(sanitizeAssistantText("")).toBe("");
  });
});

describe("sanitizeErrorMessage", () => {
  it("keeps a user-facing outage message", () => {
    const outage =
      "I'm sorry, but the global opportunity database is currently offline. Please try again later.";
    expect(sanitizeErrorMessage(outage)).toBe(outage);
  });

  it("replaces a bare machine token", () => {
    expect(sanitizeErrorMessage("rate_limited")).toBe(GENERIC_ASSISTANT_ERROR);
  });

  it("replaces a stringified exception", () => {
    expect(
      sanitizeErrorMessage("Internal supervisor error: TimeoutError()"),
    ).toBe(GENERIC_ASSISTANT_ERROR);
  });

  it("replaces a non-string", () => {
    expect(sanitizeErrorMessage(undefined)).toBe(GENERIC_ASSISTANT_ERROR);
    expect(sanitizeErrorMessage(null)).toBe(GENERIC_ASSISTANT_ERROR);
  });
});

describe("presentableSources", () => {
  it("drops RAG's internal seed URLs", () => {
    expect(
      presentableSources([
        "https://goa.internal/seed/demo-program/tu-berlin-msc-cs",
      ]),
    ).toEqual([]);
  });

  it("drops retrieval internals that are not URLs at all", () => {
    expect(presentableSources(["doc_412#chunk-7", "", "  "])).toEqual([]);
  });

  it("keeps a real external citation and labels it by host", () => {
    expect(
      presentableSources(["https://www.tu.berlin/en/studying/msc-cs?x=1"]),
    ).toEqual([
      { href: "https://www.tu.berlin/en/studying/msc-cs?x=1", label: "tu.berlin" },
    ]);
  });

  it("de-duplicates repeated citations", () => {
    const sources = ["https://example.org/a", "https://example.org/a"];
    expect(presentableSources(sources)).toHaveLength(1);
  });
});
