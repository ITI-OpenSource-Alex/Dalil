import { afterEach, describe, expect, it, vi } from "vitest";

import {
  authenticatedFetch,
  resetAuthRefreshForTests,
} from "@/lib/authenticated-fetch";

afterEach(() => {
  vi.unstubAllGlobals();
  resetAuthRefreshForTests();
});

describe("authenticatedFetch", () => {
  it("refreshes an expired access cookie and retries the request once", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response("unauthorized", { status: 401 }))
      .mockResolvedValueOnce(new Response("{}", { status: 200 }))
      .mockResolvedValueOnce(new Response('{"submitted":true}', { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    const response = await authenticatedFetch(
      "http://localhost:8080/api/exam/listening/session-1/submit",
      { method: "PUT", body: '{"answers":{}}' },
    );

    expect(response.status).toBe(200);
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(fetchMock.mock.calls[1][0]).toBe(
      "http://localhost:8080/auth/refresh",
    );
    expect(fetchMock.mock.calls[2][0]).toContain("/listening/session-1/submit");
    expect(fetchMock.mock.calls[2][1]).toEqual(
      expect.objectContaining({ credentials: "include", method: "PUT" }),
    );
  });

  it("shares one refresh when concurrent requests expire together", async () => {
    let resolveRefresh!: (response: Response) => void;
    const refreshResponse = new Promise<Response>((resolve) => {
      resolveRefresh = resolve;
    });
    let protectedCalls = 0;
    let refreshCalls = 0;

    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        if (String(input).endsWith("/auth/refresh")) {
          refreshCalls += 1;
          return refreshResponse;
        }
        protectedCalls += 1;
        return Promise.resolve(
          new Response("{}", { status: protectedCalls <= 2 ? 401 : 200 }),
        );
      }),
    );

    const first = authenticatedFetch("http://localhost:8080/api/exam/a");
    const second = authenticatedFetch("http://localhost:8080/api/exam/b");
    await vi.waitFor(() => expect(refreshCalls).toBe(1));
    resolveRefresh(new Response("{}", { status: 200 }));

    expect((await first).status).toBe(200);
    expect((await second).status).toBe(200);
    expect(refreshCalls).toBe(1);
  });

  it("returns the original 401 when refresh is unavailable", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response("unauthorized", { status: 401 }))
      .mockResolvedValueOnce(new Response("expired", { status: 401 }));
    vi.stubGlobal("fetch", fetchMock);

    const response = await authenticatedFetch("http://localhost:8080/api/exam/a");

    expect(response.status).toBe(401);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});
