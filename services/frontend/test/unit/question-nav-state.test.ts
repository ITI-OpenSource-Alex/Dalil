import { describe, expect, it } from "vitest";
import {
  navCircleAriaLabel,
  navCircleClassName,
  navLegendSwatchClassName,
} from "@/lib/question-nav-state";

describe("navCircleClassName", () => {
  it("marks unanswered with a strong border and surface fill", () => {
    const cls = navCircleClassName({ answered: false, active: false });
    expect(cls).toContain("bg-surface");
    expect(cls).toContain("border-border-strong");
    expect(cls).not.toContain("bg-brand");
    // Current-state ring only — focus-visible:ring-2 is always present.
    expect(cls).not.toContain("ring-2 ring-brand-muted");
  });

  it("marks answered with brand fill", () => {
    const cls = navCircleClassName({ answered: true, active: false });
    expect(cls).toContain("bg-brand");
    expect(cls).toContain("text-fg-on-brand");
    expect(cls).toContain("border-brand");
    expect(cls).not.toContain("ring-2 ring-brand-muted");
  });

  it("adds a current ring on unanswered", () => {
    const cls = navCircleClassName({ answered: false, active: true });
    expect(cls).toContain("bg-surface");
    expect(cls).toContain("ring-2 ring-brand-muted");
    expect(cls).toContain("border-brand");
  });

  it("stacks current ring on answered fill", () => {
    const cls = navCircleClassName({ answered: true, active: true });
    expect(cls).toContain("bg-brand");
    expect(cls).toContain("ring-2 ring-brand-muted");
  });
});

describe("navCircleAriaLabel", () => {
  it("describes unanswered", () => {
    expect(
      navCircleAriaLabel({
        questionNumber: 3,
        answered: false,
        active: false,
      }),
    ).toBe("Question 3, unanswered");
  });

  it("describes answered and current", () => {
    expect(
      navCircleAriaLabel({
        questionNumber: 1,
        answered: true,
        active: true,
      }),
    ).toBe("Question 1, answered, current");
  });
});

describe("navLegendSwatchClassName", () => {
  it("returns distinct classes per legend kind", () => {
    expect(navLegendSwatchClassName("answered")).toContain("bg-brand");
    expect(navLegendSwatchClassName("unanswered")).toContain("bg-surface");
    expect(navLegendSwatchClassName("current")).toContain("ring-2");
  });
});
