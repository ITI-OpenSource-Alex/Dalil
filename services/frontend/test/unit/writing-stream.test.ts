import { describe, it, expect, vi, afterEach } from "vitest";
import { streamWritingEvaluation } from "@/lib/writing-stream";
import { isSubscriptionRequiredError } from "@/lib/subscription";

describe("streamWritingEvaluation", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("sends credentials so the Gateway's auth cookie is attached", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      body: {
        getReader: () => ({
          read: async () => ({ done: true, value: undefined }),
        }),
      },
    });
    vi.stubGlobal("fetch", fetchMock);

    await streamWritingEvaluation("https://gateway.example/api/writing/essays/1/evaluate", () => {});

    expect(fetchMock).toHaveBeenCalledWith(
      "https://gateway.example/api/writing/essays/1/evaluate",
      expect.objectContaining({ credentials: "include" }),
    );
  });

  it("rejects with a message that includes the HTTP status on a non-ok response", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      // The failure path now reads the body (see throwForResponse in
      // lib/subscription.ts) so it can tell a paid-tier refusal apart from a
      // real fault, so the stub needs a real Response's text().
      text: async () => "",
    });
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      streamWritingEvaluation("https://gateway.example/api/writing/essays/1/evaluate", () => {}),
    ).rejects.toThrow(/401/);
  });

  it("delivers the final event even without a trailing blank line", async () => {
    // The last SSE event has no reason to be followed by "\n\n" -- the
    // connection just closes right after it. Regression guard for the bug
    // where that event sat in the parser's buffer waiting for a separator
    // that never arrived and was silently dropped once the reader reported
    // done: true (found via /practice/writing e2e tests, which mocked
    // exactly this shape).
    const encoder = new TextEncoder();
    const body =
      'data: {"type":"criterion","criterion":"grammar","band":7,"feedback":"Good grammar"}\n\n' +
      'data: {"type":"complete","essay_id":"1","overall_band":7,"evaluations":{}}\n';
    let sent = false;
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      body: {
        getReader: () => ({
          read: async () => {
            if (sent) return { done: true, value: undefined };
            sent = true;
            return { done: false, value: encoder.encode(body) };
          },
        }),
      },
    });
    vi.stubGlobal("fetch", fetchMock);

    const events: string[] = [];
    await streamWritingEvaluation(
      "https://gateway.example/api/writing/essays/1/evaluate",
      (event) => events.push(event.type),
    );

    expect(events).toEqual(["criterion", "complete"]);
  });

  it("rejects with a SubscriptionRequiredError on the Gateway's paid-tier 403", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 403,
      text: async () =>
        JSON.stringify({
          error: "subscription_required",
          upgradeUrl: "https://billing.example/upgrade",
        }),
    });
    vi.stubGlobal("fetch", fetchMock);

    // The distinction that matters: a paywall must not reach the user as
    // "Unable to start writing evaluation (status 403)".
    await expect(
      streamWritingEvaluation("https://gateway.example/api/writing/essays/1/evaluate", () => {}),
    ).rejects.toSatisfy(isSubscriptionRequiredError);
  });
});
