import { describe, expect, it } from "vitest";
import {
  compactFacts,
  defaultExplanationPrompt,
  fact,
  type ExplanationContext,
} from "@/lib/explanation-context";

describe("explanation context helpers", () => {
  it("builds an editable prompt from the visible claim", () => {
    const context: ExplanationContext = {
      kind: "cv_review",
      title: "your CV experience score 62/100",
      facts: [{ label: "Experience score", value: "62/100" }],
    };

    expect(defaultExplanationPrompt(context)).toBe(
      "Explain your cv experience score 62/100. Show me which evidence affected it, what it does not prove, and what I can do next.",
    );
  });

  it("drops missing facts and bounds every browser-supplied field", () => {
    const facts = compactFacts([
      fact("A".repeat(100), "B".repeat(600), `https://example.com/${"c".repeat(600)}`),
      fact("Missing", null),
      false,
    ]);

    expect(facts).toHaveLength(1);
    expect(facts[0].label).toHaveLength(80);
    expect(facts[0].value).toHaveLength(500);
    expect(facts[0].sourceUrl).toHaveLength(500);
  });
});
