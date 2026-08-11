import { afterEach, describe, expect, it, vi } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";

const apiMock = vi.hoisted(() => ({ searchOpportunities: vi.fn() }));
vi.mock("@/lib/opportunities-api", async (importOriginal) => {
  const actual =
    await importOriginal<typeof import("@/lib/opportunities-api")>();
  return { ...actual, searchOpportunities: apiMock.searchOpportunities };
});

const { useOpportunityMatches } =
  await import("@/components/profile/use-opportunity-matches");

const PROGRAM = {
  programId: "prog-1",
  programName: "MSc Computer Science",
  university: "TU Munich",
  country: "Germany",
  deadline: null,
  result: { score: 85, blocked_by: null },
};

afterEach(() => {
  vi.clearAllMocks();
});

describe("useOpportunityMatches", () => {
  it("searches once when it is enabled and visible", async () => {
    apiMock.searchOpportunities.mockResolvedValue([PROGRAM]);

    const { result } = renderHook(() =>
      useOpportunityMatches({ enabled: true, visible: true, savedAt: 0 }),
    );

    await waitFor(() => expect(result.current.status).toBe("success"));
    expect(result.current.programs).toHaveLength(1);
    expect(apiMock.searchOpportunities).toHaveBeenCalledTimes(1);
  });

  it("does not search while the matches surface is hidden", async () => {
    apiMock.searchOpportunities.mockResolvedValue([]);

    renderHook(() =>
      useOpportunityMatches({ enabled: true, visible: false, savedAt: 0 }),
    );

    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(apiMock.searchOpportunities).not.toHaveBeenCalled();
  });

  it("does not search again when visibility toggles without a save", async () => {
    apiMock.searchOpportunities.mockResolvedValue([PROGRAM]);

    const { result, rerender } = renderHook(
      ({ visible }) =>
        useOpportunityMatches({ enabled: true, visible, savedAt: 0 }),
      { initialProps: { visible: true } },
    );
    await waitFor(() => expect(result.current.status).toBe("success"));

    rerender({ visible: false });
    rerender({ visible: true });

    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(apiMock.searchOpportunities).toHaveBeenCalledTimes(1);
  });

  it("re-ranks once when the profile was saved and the surface is shown again", async () => {
    apiMock.searchOpportunities.mockResolvedValue([PROGRAM]);

    const { result, rerender } = renderHook(
      ({ visible, savedAt }) =>
        useOpportunityMatches({ enabled: true, visible, savedAt }),
      { initialProps: { visible: true, savedAt: 0 } },
    );
    await waitFor(() => expect(result.current.status).toBe("success"));

    // Editing happens on another tab: two saves, no search.
    rerender({ visible: false, savedAt: 1 });
    rerender({ visible: false, savedAt: 2 });
    expect(apiMock.searchOpportunities).toHaveBeenCalledTimes(1);

    rerender({ visible: true, savedAt: 2 });
    await waitFor(() =>
      expect(apiMock.searchOpportunities).toHaveBeenCalledTimes(2),
    );
  });

  it("reports an incomplete profile without spending a search", async () => {
    const { result } = renderHook(() =>
      useOpportunityMatches({ enabled: false, visible: true, savedAt: 0 }),
    );

    await waitFor(() =>
      expect(result.current.status).toBe("profile-incomplete"),
    );
    expect(apiMock.searchOpportunities).not.toHaveBeenCalled();
  });

  it("surfaces the wait when the hourly search limit is hit", async () => {
    const { RateLimitedError } = await import("@/lib/opportunities-api");
    apiMock.searchOpportunities.mockRejectedValue(new RateLimitedError(120));

    const { result } = renderHook(() =>
      useOpportunityMatches({ enabled: true, visible: true, savedAt: 0 }),
    );

    await waitFor(() => expect(result.current.status).toBe("rate-limited"));
    expect(result.current.retryAfter).toBe("2 minutes");
  });
});
