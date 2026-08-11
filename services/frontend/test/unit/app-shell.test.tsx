import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";

const pathnameMock = vi.hoisted(() => ({ value: "/exam" }));

vi.mock("next/navigation", () => ({
  usePathname: () => pathnameMock.value,
}));

vi.mock("@/components/ui/sidebar", () => ({
  Sidebar: () => (
    <aside data-testid="app-sidebar">
      <nav aria-label="Main">Main nav</nav>
    </aside>
  ),
}));

const { AppShell } = await import("@/components/app-shell");

describe("AppShell", () => {
  beforeEach(() => {
    pathnameMock.value = "/exam";
  });

  it("renders the app sidebar on non-focus routes", () => {
    pathnameMock.value = "/exam";
    render(
      <AppShell>
        <div>Hub content</div>
      </AppShell>,
    );
    expect(screen.getByTestId("app-sidebar")).toBeInTheDocument();
    expect(screen.getByText("Hub content")).toBeInTheDocument();
  });

  it("omits the app sidebar on /exam/shell", () => {
    pathnameMock.value = "/exam/shell";
    render(
      <AppShell>
        <div>Exam workspace</div>
      </AppShell>,
    );
    expect(screen.queryByTestId("app-sidebar")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("navigation", { name: "Main" }),
    ).not.toBeInTheDocument();
    expect(screen.getByText("Exam workspace")).toBeInTheDocument();
  });

  it("omits the app sidebar when pathname has a trailing slash", () => {
    pathnameMock.value = "/exam/shell/";
    render(
      <AppShell>
        <div>Exam workspace</div>
      </AppShell>,
    );
    expect(screen.queryByTestId("app-sidebar")).not.toBeInTheDocument();
  });

  it("keeps the sidebar on /exam/results", () => {
    pathnameMock.value = "/exam/results";
    render(
      <AppShell>
        <div>Results</div>
      </AppShell>,
    );
    expect(screen.getByTestId("app-sidebar")).toBeInTheDocument();
  });
});
