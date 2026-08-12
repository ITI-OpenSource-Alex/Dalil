import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import StreamingMessage from "@/components/chat/streaming-message";

describe("StreamingMessage Markdown presentation", () => {
  it("renders assistant emphasis and lists as structured content", () => {
    const { container } = render(
      <StreamingMessage
        markdown
        content={[
          "It is shown as **100% fit** because:",
          "",
          "- Eligibility: **40 points**",
          "- Subject fit: **35 points**",
        ].join("\n")}
      />,
    );

    expect(screen.getByText("100% fit").tagName).toBe("STRONG");
    const list = container.querySelector("ul");
    expect(list).not.toBeNull();
    expect(within(list as HTMLUListElement).getAllByRole("listitem")).toHaveLength(2);
    expect(screen.queryByText(/\*\*100% fit\*\*/)).not.toBeInTheDocument();
  });

  it("keeps user-authored Markdown characters literal when Markdown is disabled", () => {
    render(<StreamingMessage content="Please explain **this** exactly." />);

    expect(screen.getByText("Please explain **this** exactly.")).toBeVisible();
    expect(screen.queryByText("this", { selector: "strong" })).not.toBeInTheDocument();
  });

  it("does not turn unsafe link protocols into clickable links", () => {
    render(
      <StreamingMessage
        markdown
        content="[Unsafe action](javascript:alert('no'))"
      />,
    );

    expect(screen.getByText("Unsafe action").closest("a")).toBeNull();
  });
});
