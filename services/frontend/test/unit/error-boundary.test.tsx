import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import RootError from "@/app/error";

/**
 * The root error boundary must render *inside* the root layout.
 *
 * This file exists because it did not, and the consequence was worse than
 * having no boundary: app/error.tsx emitted its own <html>/<body>, which the
 * root layout's <body> then contained. React refuses to mount a second <html>
 * ("You are mounting a new html component when a previous one has not first
 * unmounted"), so the recovery UI never hydrated and "Try again" could not
 * recover -- any incidental error became a permanent "Something went wrong".
 *
 * The distinction is a Next.js App Router convention and is easy to get wrong
 * again:
 *
 *   app/error.tsx        renders inside the root layout -> ordinary content
 *   app/global-error.tsx replaces the root layout       -> owns <html>/<body>
 */
describe("app/error.tsx (root error boundary)", () => {
  const props = { error: new Error("boom"), reset: () => {} };

  it("renders no <html> or <body> of its own", () => {
    const { container } = render(<RootError {...props} />);

    expect(container.querySelector("html")).toBeNull();
    expect(container.querySelector("body")).toBeNull();
  });

  it("still shows a recoverable, on-brand message", () => {
    render(<RootError {...props} />);

    expect(
      screen.getByRole("heading", { name: "Something went wrong" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to Chat" })).toHaveAttribute(
      "href",
      "/chat",
    );
  });

  it("retries through reset(), which is the only way out of a crashed tree", async () => {
    const reset = vi.fn();
    render(<RootError error={props.error} reset={reset} />);

    await userEvent.click(screen.getByRole("button", { name: "Try again" }));

    expect(reset).toHaveBeenCalledTimes(1);
  });
});
