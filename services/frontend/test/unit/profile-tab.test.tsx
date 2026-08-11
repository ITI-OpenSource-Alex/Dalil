import { afterEach, describe, expect, it, vi } from "vitest";
import { renderHook, act } from "@testing-library/react";

const nav = vi.hoisted(() => ({
  params: new URLSearchParams(),
  replace: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: nav.replace }),
  usePathname: () => "/profile",
  useSearchParams: () => nav.params,
}));

const { useProfileTab } = await import("@/components/profile/use-profile-tab");

afterEach(() => {
  nav.params = new URLSearchParams();
  vi.clearAllMocks();
});

describe("useProfileTab", () => {
  it("defaults to matches when the URL says nothing", () => {
    const { result } = renderHook(() => useProfileTab());
    expect(result.current.tab).toBe("matches");
  });

  it("reads the tab out of the query string", () => {
    nav.params = new URLSearchParams("tab=edit");
    const { result } = renderHook(() => useProfileTab());
    expect(result.current.tab).toBe("edit");
  });

  it("falls back to matches for a tab name it does not know", () => {
    nav.params = new URLSearchParams("tab=nonsense");
    const { result } = renderHook(() => useProfileTab());
    expect(result.current.tab).toBe("matches");
  });

  it("writes the tab to the URL without adding history entries", () => {
    const { result } = renderHook(() => useProfileTab());
    act(() => result.current.setTab("progress"));
    expect(nav.replace).toHaveBeenCalledWith("/profile?tab=progress", {
      scroll: false,
    });
  });

  it("drops the param again when returning to the default tab", () => {
    nav.params = new URLSearchParams("tab=edit");
    const { result } = renderHook(() => useProfileTab());
    act(() => result.current.setTab("matches"));
    expect(nav.replace).toHaveBeenCalledWith("/profile", { scroll: false });
  });

  it("keeps unrelated query params intact", () => {
    nav.params = new URLSearchParams("ref=email");
    const { result } = renderHook(() => useProfileTab());
    act(() => result.current.setTab("edit"));
    expect(nav.replace).toHaveBeenCalledWith("/profile?ref=email&tab=edit", {
      scroll: false,
    });
  });
});
