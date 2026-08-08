import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { UpgradeDialog, UpgradeProvider, useUpgradePrompt } from "@/components/subscription/upgrade-dialog";
import {
  DEFAULT_UPGRADE_URL,
  SubscriptionRequiredError,
  paidFeatureCopy,
} from "@/lib/subscription";

/**
 * GOA-039 did not build a new upgrade modal -- this one already existed and
 * already satisfied the first acceptance criterion. What changed is where its
 * call to action lands. These tests pin both halves: the modal still explains
 * the feature, and it now points at a route that exists.
 */

describe("UpgradeDialog", () => {
  it("lists what the user gets for the feature they were refused", () => {
    render(
      <UpgradeDialog
        open
        onOpenChange={() => {}}
        feature="exam"
        upgradeUrl={DEFAULT_UPGRADE_URL}
      />,
    );

    const copy = paidFeatureCopy("exam");
    expect(screen.getByText(copy.title)).toBeInTheDocument();
    for (const benefit of copy.benefits) {
      expect(screen.getByText(benefit)).toBeInTheDocument();
    }
  });

  it("sends the upgrade CTA to /pricing", () => {
    render(
      <UpgradeDialog
        open
        onOpenChange={() => {}}
        feature="cv-review"
        upgradeUrl={DEFAULT_UPGRADE_URL}
      />,
    );

    expect(
      screen.getByRole("link", { name: /Upgrade to Dalil Pro/ }),
    ).toHaveAttribute("href", "/pricing");
  });

  it("still honours an absolute URL named by the Gateway, in a new tab", () => {
    render(
      <UpgradeDialog
        open
        onOpenChange={() => {}}
        upgradeUrl="https://billing.example/upgrade"
      />,
    );

    const link = screen.getByRole("link", { name: /Upgrade to Dalil Pro/ });
    expect(link).toHaveAttribute("href", "https://billing.example/upgrade");
    expect(link).toHaveAttribute("target", "_blank");
  });
});

describe("useUpgradePrompt", () => {
  function Harness() {
    const upgrade = useUpgradePrompt();
    return (
      <>
        <button onClick={() => upgrade.show("exam")}>show</button>
        <button
          onClick={() => {
            const handled = upgrade.handle(
              new SubscriptionRequiredError(null, "cv-review"),
            );
            if (!handled) throw new Error("should have been handled");
          }}
        >
          handle
        </button>
      </>
    );
  }

  it("opens the dialog for a named feature", async () => {
    render(
      <UpgradeProvider>
        <Harness />
      </UpgradeProvider>,
    );

    await userEvent.click(screen.getByRole("button", { name: "show" }));

    expect(screen.getByText(paidFeatureCopy("exam").title)).toBeInTheDocument();
  });

  it("turns a paid-tier refusal into the dialog, defaulting to /pricing", async () => {
    render(
      <UpgradeProvider>
        <Harness />
      </UpgradeProvider>,
    );

    await userEvent.click(screen.getByRole("button", { name: "handle" }));

    expect(
      screen.getByText(paidFeatureCopy("cv-review").title),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: /Upgrade to Dalil Pro/ }),
    ).toHaveAttribute("href", "/pricing");
  });

  it("ignores an error that is not a paywall", async () => {
    const onResult = vi.fn();

    function OtherHarness() {
      const upgrade = useUpgradePrompt();
      return (
        <button
          onClick={() => onResult(upgrade.handle(new Error("upstream exploded")))}
        >
          try
        </button>
      );
    }

    render(
      <UpgradeProvider>
        <OtherHarness />
      </UpgradeProvider>,
    );

    await userEvent.click(screen.getByRole("button", { name: "try" }));

    // Returns false so the call site can render its own error instead.
    expect(onResult).toHaveBeenCalledWith(false);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
