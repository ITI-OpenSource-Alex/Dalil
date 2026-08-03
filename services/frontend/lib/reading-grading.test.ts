import { describe, expect, it } from "vitest";
import {
  compareFillInBlankAnswers,
  normalizeFillInBlankAnswer,
} from "./reading-grading";

describe("FillInBlank comparison", () => {
  it("trims leading/trailing whitespace before comparing", () => {
    expect(compareFillInBlankAnswers("  minutes  ", "minutes")).toBe(true);
  });

  it("lowercases before comparing", () => {
    expect(compareFillInBlankAnswers("MINUTES", "minutes")).toBe(true);
  });

  it("trims and lowercases together", () => {
    expect(compareFillInBlankAnswers("  Minutes  ", "minutes")).toBe(true);
  });

  it("still distinguishes genuinely different answers", () => {
    expect(compareFillInBlankAnswers("minutes", "seconds")).toBe(false);
  });

  it("treats null/undefined as an empty answer", () => {
    expect(normalizeFillInBlankAnswer(null)).toBe("");
    expect(normalizeFillInBlankAnswer(undefined)).toBe("");
    expect(compareFillInBlankAnswers(null, "")).toBe(true);
  });

  it("does not collapse internal whitespace (only trims/lowercases)", () => {
    expect(compareFillInBlankAnswers("data set", "dataset")).toBe(false);
  });
});
