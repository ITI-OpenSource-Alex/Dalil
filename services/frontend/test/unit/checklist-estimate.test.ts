import { describe, it, expect } from "vitest";
import {
  estimateCompletionDate,
  ASSUMED_DAYS_PER_REMAINING_ITEM,
} from "@/lib/checklist-estimate";

describe("estimateCompletionDate", () => {
  it("returns null when there are no remaining items", () => {
    expect(estimateCompletionDate(0)).toBeNull();
  });

  it("advances by the assumed number of days per remaining item", () => {
    const today = new Date(2026, 0, 1);
    const result = estimateCompletionDate(4, today);
    expect(result).not.toBeNull();
    const expectedDays = 4 * ASSUMED_DAYS_PER_REMAINING_ITEM;
    const expected = new Date(2026, 0, 1 + expectedDays);
    expect(result?.toDateString()).toBe(expected.toDateString());
  });

  it("does not mutate the provided reference date", () => {
    const today = new Date(2026, 0, 1);
    estimateCompletionDate(2, today);
    expect(today.toDateString()).toBe(new Date(2026, 0, 1).toDateString());
  });
});
