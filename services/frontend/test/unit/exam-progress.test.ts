import { describe, expect, it } from "vitest";
import {
  estimateOverallPracticeBand,
  isExamProgressEmpty,
} from "@/lib/exam-progress";

describe("estimateOverallPracticeBand", () => {
  it("returns null when no skills have points", () => {
    expect(estimateOverallPracticeBand({})).toBeNull();
  });

  it("averages latest bands and rounds with IELTS .25-up rule", () => {
    // latest reading 6.0, latest listening 6.5 → mean 6.25 → 6.5
    expect(
      estimateOverallPracticeBand({
        reading: [
          { date: "2026-01-01", band: 5.5 },
          { date: "2026-02-01", band: 6.0 },
        ],
        listening: [{ date: "2026-02-01", band: 6.5 }],
      }),
    ).toBe(6.5);
  });

  it("uses only skills that have data (partial OK)", () => {
    expect(
      estimateOverallPracticeBand({
        reading: [{ date: "2026-01-01", band: 7.0 }],
      }),
    ).toBe(7.0);
  });
});

describe("isExamProgressEmpty", () => {
  it("is true when history empty and no progress points", () => {
    expect(isExamProgressEmpty({}, 0)).toBe(true);
  });

  it("is false when history has rows", () => {
    expect(isExamProgressEmpty({}, 1)).toBe(false);
  });
});
