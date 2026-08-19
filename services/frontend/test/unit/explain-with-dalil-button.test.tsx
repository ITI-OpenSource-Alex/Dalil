import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const chatMock = vi.hoisted(() => ({ openWithExplanation: vi.fn() }));
vi.mock("@/components/chat/dalil-chat-provider", () => ({
  useOptionalDalilChat: () => chatMock,
}));

const { ExplainWithDalilButton } = await import(
  "@/components/chat/explain-with-dalil-button"
);
const { TooltipProvider } = await import("@/components/ui/tooltip");

describe("ExplainWithDalilButton", () => {
  beforeEach(() => {
    chatMock.openWithExplanation.mockReset();
    vi.spyOn(window, "requestAnimationFrame").mockImplementation((callback) => {
      callback(0);
      return 1;
    });
  });

  it("opens Dalil with typed evidence and does not auto-send", () => {
    const context = {
      kind: "visa_requirement" as const,
      title: "Germany proof of funds",
      facts: [{ label: "Amount", value: "Official source required" }],
    };

    render(
      <TooltipProvider>
        <ExplainWithDalilButton
          context={context}
          prompt="Explain this proof-of-funds requirement."
        />
      </TooltipProvider>,
    );

    const button = screen.getByRole("button", {
      name: "Ask Dalil to explain Germany proof of funds",
    });
    expect(button).toHaveAttribute("data-explanation-kind", "visa_requirement");
    fireEvent.click(button);

    expect(chatMock.openWithExplanation).toHaveBeenCalledWith(
      "Explain this proof-of-funds requirement.",
      context,
      expect.objectContaining({ invoker: button }),
    );
  });
});
