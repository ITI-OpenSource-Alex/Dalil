import { describe, it, expect, vi, afterEach } from "vitest";
import { streamWritingEvaluation } from "@/lib/writing-stream";

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
    });
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      streamWritingEvaluation("https://gateway.example/api/writing/essays/1/evaluate", () => {}),
    ).rejects.toThrow(/401/);
  });
});
