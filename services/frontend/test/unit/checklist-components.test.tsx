import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ChecklistItemRow from "@/components/checklist/ChecklistItemRow";
import FinancialRequirements from "@/components/checklist/FinancialRequirements";
import type { ChecklistItem, FinancialRequirementItem } from "@/app/types/checklist";

describe("ChecklistItemRow", () => {
  const item: ChecklistItem = {
    itemId: "ielts_retake",
    title: "Retake IELTS",
    description: "Your score is below the program minimum.",
    category: "language",
    checked: false,
  };

  it("renders title and description", () => {
    render(<ChecklistItemRow item={item} onToggle={() => {}} />);
    expect(screen.getByText("Retake IELTS")).toBeInTheDocument();
    expect(
      screen.getByText("Your score is below the program minimum."),
    ).toBeInTheDocument();
  });

  it("calls onToggle with the flipped checked state when clicked", async () => {
    const onToggle = vi.fn();
    render(<ChecklistItemRow item={item} onToggle={onToggle} />);
    await userEvent.click(screen.getByRole("checkbox"));
    expect(onToggle).toHaveBeenCalledWith(true);
  });

  it("does not render a lock icon (no blocked field exists on the backend item)", () => {
    render(<ChecklistItemRow item={item} onToggle={() => {}} />);
    expect(screen.queryByLabelText(/blocked/i)).not.toBeInTheDocument();
  });
});

describe("FinancialRequirements", () => {
  it("renders nothing when there are no items (omits the phase entirely)", () => {
    const { container } = render(<FinancialRequirements items={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders only fields present in the structured response, verbatim", () => {
    const items: FinancialRequirementItem[] = [
      {
        type: "informational",
        country: "Germany",
        issuingBody: "Fintiba",
        message: "requires proof of 11904 EUR per year via blocked_account",
        sourceUrl: "https://www.fintiba.com/blocked-account/",
        lastVerifiedAt: "2026-06-01T00:00:00Z",
      },
    ];
    render(<FinancialRequirements items={items} />);
    expect(screen.getByText("Germany — Fintiba")).toBeInTheDocument();
    expect(
      screen.getByText("requires proof of 11904 EUR per year via blocked_account"),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Official source" })).toHaveAttribute(
      "href",
      "https://www.fintiba.com/blocked-account/",
    );
  });
});
