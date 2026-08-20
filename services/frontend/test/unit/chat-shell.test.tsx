import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

/* ------------------------------------------------------------------ *
 * Since Phase D (docs/IA-REDESIGN-PROPOSAL.md), ChatShell no longer owns the
 * microphone, an AudioContext or a speaking WebSocket -- that machinery moved
 * to components/practice/speaking-practice-panel.tsx, exercised by its own
 * tests. What's left here is the message pipeline and the router push on the
 * classifier's writing_url/speaking_url events, so this file mocks just
 * next/navigation (ChatShell isn't rendered inside a real Next.js App Router
 * in a unit test) and the profile fetch.
 * ------------------------------------------------------------------ */

const routerMock = vi.hoisted(() => ({ push: vi.fn() }));
vi.mock("next/navigation", () => ({
  useRouter: () => routerMock,
}));

const profileMock = vi.hoisted(() => ({ getMyProfile: vi.fn() }));
vi.mock("@/lib/profile-api", () => profileMock);

const { default: ChatShell } = await import("@/components/chat/chat-shell");

/** An SSE body that emits `chunks` and then closes, framed the way
 *  sse-starlette frames events (CRLF, `event:` + `data:` lines). */
function sseResponse(chunks: string[]): Response {
  const encoder = new TextEncoder();
  let index = 0;
  return {
    ok: true,
    status: 200,
    body: {
      getReader: () => ({
        read: async () => {
          if (index >= chunks.length) return { done: true, value: undefined };
          const value = encoder.encode(chunks[index]);
          index += 1;
          return { done: false, value };
        },
      }),
    },
  } as unknown as Response;
}

function tokenEvent(text: string): string {
  return `event: token\r\ndata: ${JSON.stringify({ type: "token", content: text })}\r\n\r\n`;
}

function statusEvent(stage: string, message: string): string {
  return `event: status\r\ndata: ${JSON.stringify({ type: "status", stage, message })}\r\n\r\n`;
}

function errorEvent(error: string): string {
  return `event: error\r\ndata: ${JSON.stringify({ type: "error", error })}\r\n\r\n`;
}

describe("ChatShell message pipeline", () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    profileMock.getMyProfile.mockResolvedValue({
      id: "user-1",
      email: "amina@example.com",
      subscriptionTier: "free",
      isVerified: true,
      profile: null,
    });

    fetchMock = vi.fn(async (url: string) => {
      if (String(url).includes("/history")) {
        return { ok: true, json: async () => [] } as unknown as Response;
      }
      return sseResponse([tokenEvent("Hello "), tokenEvent("there.")]);
    });
    vi.stubGlobal("fetch", fetchMock);
    window.sessionStorage.clear();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.clearAllMocks();
  });

  it("issues exactly one chat request and renders one reply per send", async () => {
    const user = userEvent.setup();
    render(<ChatShell />);

    const input = await screen.findByTestId("chat-input");
    // Readiness is "identity resolved", not "Send enabled" -- Send is disabled
    // whenever the textarea is empty, which it is before we type.
    await screen.findByText("amina@example.com");

    await user.type(input, "Find me a Master's in Germany");
    await user.click(screen.getByTestId("send-message-button"));

    await waitFor(() =>
      expect(screen.getByText(/Hello there\./)).toBeInTheDocument(),
    );

    const chatCalls = fetchMock.mock.calls.filter(
      (call) => String(call[0]).endsWith("/api/chat"),
    );
    expect(chatCalls).toHaveLength(1);

    // The core assertion of item 8B: one user message in, one assistant
    // message out. The welcome message is an assistant bubble too, hence 2.
    expect(screen.getAllByTestId("user-message")).toHaveLength(1);
    expect(screen.getAllByTestId("assistant-message")).toHaveLength(2);
  });

  it("keeps a visible progress animation until the first answer token", async () => {
    let release!: () => void;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });

    fetchMock.mockImplementation(async (url: string) => {
      if (String(url).includes("/history")) {
        return { ok: true, json: async () => [] } as unknown as Response;
      }
      const encoder = new TextEncoder();
      let index = 0;
      return {
        ok: true,
        status: 200,
        body: {
          getReader: () => ({
            read: async () => {
              if (index === 0) {
                index += 1;
                return {
                  done: false,
                  value: encoder.encode(
                    statusEvent("retrieving", "Searching trusted sources…"),
                  ),
                };
              }
              if (index === 1) {
                index += 1;
                await gate;
                return {
                  done: false,
                  value: encoder.encode(tokenEvent("A grounded answer.")),
                };
              }
              return { done: true, value: undefined };
            },
          }),
        },
      } as unknown as Response;
    });

    const user = userEvent.setup();
    render(<ChatShell />);
    const input = await screen.findByTestId("chat-input");
    await screen.findByText("amina@example.com");

    await user.type(input, "What are Germany's visa requirements?{Enter}");

    expect(
      await screen.findByRole("status", { name: /Searching trusted sources/i }),
    ).toBeVisible();
    release();
    expect(await screen.findByText("A grounded answer.")).toBeVisible();
    await waitFor(() => expect(screen.queryByRole("status")).toBeNull());
  });

  it("shows removable turn-scoped evidence and sends it separately from editable text", async () => {
    const user = userEvent.setup();
    const clearContext = vi.fn();
    const explanationContext = {
      kind: "programme_match" as const,
      title: "MSc Computer Science 91% fit",
      subjectId: "tum-cs",
      facts: [
        { label: "Fit score", value: "91%" },
        { label: "University", value: "Technical University of Munich" },
      ],
      limitations: ["A fit score is not an admission decision."],
    };

    render(
      <ChatShell
        draft="Why is this a strong fit?"
        onDraftChange={vi.fn()}
        explanationContext={explanationContext}
        onClearExplanationContext={clearContext}
      />,
    );

    await screen.findByText("amina@example.com");
    expect(screen.getByTestId("explanation-context-card")).toHaveTextContent(
      "MSc Computer Science 91% fit",
    );

    await user.click(screen.getByTestId("send-message-button"));

    await waitFor(() => {
      const chatCall = fetchMock.mock.calls.find((call) =>
        String(call[0]).endsWith("/api/chat"),
      );
      expect(chatCall).toBeDefined();
      const body = JSON.parse(String((chatCall?.[1] as RequestInit).body));
      expect(body.message).toBe("Why is this a strong fit?");
      expect(body.explanationContext).toEqual(explanationContext);
    });
    expect(clearContext).toHaveBeenCalledOnce();
  });

  it("refuses a second send while a reply is still streaming", async () => {
    // A stream that never completes until we let it, so the second submit
    // lands squarely mid-turn -- which is exactly how the duplicate-reply
    // bug was reproduced by hand (Enter twice, or Enter then Send).
    let release!: () => void;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });

    fetchMock.mockImplementation(async (url: string) => {
      if (String(url).includes("/history")) {
        return { ok: true, json: async () => [] } as unknown as Response;
      }
      const encoder = new TextEncoder();
      let sent = false;
      return {
        ok: true,
        status: 200,
        body: {
          getReader: () => ({
            read: async () => {
              if (!sent) {
                sent = true;
                return { done: false, value: encoder.encode(tokenEvent("Working")) };
              }
              await gate;
              return { done: true, value: undefined };
            },
          }),
        },
      } as unknown as Response;
    });

    const user = userEvent.setup();
    render(<ChatShell />);

    const input = await screen.findByTestId("chat-input");
    // Readiness is "identity resolved", not "Send enabled" -- Send is disabled
    // whenever the textarea is empty, which it is before we type.
    await screen.findByText("amina@example.com");

    await user.type(input, "first question{Enter}");
    await waitFor(() => expect(screen.getByText(/Working/)).toBeInTheDocument());

    // Type and submit again while the first turn is mid-flight.
    await user.type(input, "second question{Enter}");
    await user.click(screen.getByTestId("send-message-button"));

    const chatCalls = fetchMock.mock.calls.filter(
      (call) => String(call[0]).endsWith("/api/chat"),
    );
    expect(chatCalls).toHaveLength(1);
    expect(screen.getAllByTestId("user-message")).toHaveLength(1);

    release();
    await waitFor(() =>
      expect(screen.getByTestId("send-message-button")).not.toBeDisabled(),
    );
  });

  it("never renders a stringified backend exception", async () => {
    fetchMock.mockImplementation(async (url: string) => {
      if (String(url).includes("/history")) {
        return { ok: true, json: async () => [] } as unknown as Response;
      }
      // The exact shape orchestration used to emit before this work.
      return sseResponse([
        errorEvent("Internal supervisor error: httpx.ConnectError to http://rag:8001"),
      ]);
    });

    const user = userEvent.setup();
    render(<ChatShell />);

    const input = await screen.findByTestId("chat-input");
    // Readiness is "identity resolved", not "Send enabled" -- Send is disabled
    // whenever the textarea is empty, which it is before we type.
    await screen.findByText("amina@example.com");

    await user.type(input, "hello{Enter}");

    await waitFor(() =>
      expect(screen.getByText(/Something went wrong/i)).toBeInTheDocument(),
    );
    expect(screen.queryByText(/Internal supervisor error/)).toBeNull();
    expect(screen.queryByText(/rag:8001/)).toBeNull();
  });

  it("does not render the internal routing label with the reply", async () => {
    fetchMock.mockImplementation(async (url: string) => {
      if (String(url).includes("/history")) {
        return { ok: true, json: async () => [] } as unknown as Response;
      }
      return sseResponse([
        `event: metadata\r\ndata: ${JSON.stringify({
          type: "metadata",
          intent: "RAG",
          confidence: 0.92,
        })}\r\n\r\n`,
        tokenEvent("Berlin has several options."),
      ]);
    });

    const user = userEvent.setup();
    render(<ChatShell />);

    const input = await screen.findByTestId("chat-input");
    // Readiness is "identity resolved", not "Send enabled" -- Send is disabled
    // whenever the textarea is empty, which it is before we type.
    await screen.findByText("amina@example.com");

    await user.type(input, "hello{Enter}");

    await waitFor(() =>
      expect(screen.getByText(/Berlin has several options\./)).toBeInTheDocument(),
    );
    // "Route: RAG" used to be rendered under every assistant reply.
    expect(screen.queryByText(/Route:/)).toBeNull();
    expect(screen.queryByText(/\bRAG\b/)).toBeNull();
  });
});
