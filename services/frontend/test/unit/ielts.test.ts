import { describe, expect, it } from "vitest";
import {
  computeOverallBand,
  formatBand,
  isValidBand,
  parseBand,
  roundToBand,
} from "@/lib/ielts";

describe("isValidBand", () => {
  it.each([0, 4, 6.5, 7, 9])("accepts the reportable band %s", (value) => {
    expect(isValidBand(value)).toBe(true);
  });

  it.each([-0.5, 9.5, 6.4, 6.25, NaN, Infinity])(
    "rejects %s",
    (value) => {
      expect(isValidBand(value)).toBe(false);
    },
  );
});

describe("parseBand", () => {
  it("returns null for empty input rather than 0", () => {
    // 0 is a real IELTS band, so conflating "not entered" with "band 0" would
    // persist a score the candidate never claimed.
    expect(parseBand("")).toBeNull();
    expect(parseBand("   ")).toBeNull();
  });

  it("returns null for an unreportable value", () => {
    expect(parseBand("6.4")).toBeNull();
    expect(parseBand("12")).toBeNull();
    expect(parseBand("abc")).toBeNull();
  });

  it("parses a valid band", () => {
    expect(parseBand("6.5")).toBe(6.5);
    expect(parseBand(" 7 ")).toBe(7);
  });
});

describe("roundToBand", () => {
  // The rule the wizard used to ask candidates to apply in their heads.
  it("rounds a .25 mean up to the next half band", () => {
    expect(roundToBand(6.25)).toBe(6.5);
  });

  it("rounds a .75 mean up to the next whole band", () => {
    expect(roundToBand(6.75)).toBe(7);
  });

  it("rounds a .1 mean down", () => {
    expect(roundToBand(6.1)).toBe(6);
  });

  it("rounds a .4 mean to the nearest half", () => {
    expect(roundToBand(6.4)).toBe(6.5);
  });
});

describe("computeOverallBand", () => {
  it("returns null while any section is missing", () => {
    // A half-filled form must not show a confident band that will change on
    // the next keystroke.
    expect(
      computeOverallBand({
        listening: 7,
        reading: 6.5,
        writing: null,
        speaking: 6,
      }),
    ).toBeNull();
  });

  it("returns null when a section holds an unreportable value", () => {
    expect(
      computeOverallBand({
        listening: 7,
        reading: 6.4,
        writing: 6,
        speaking: 6,
      }),
    ).toBeNull();
  });

  it("computes the IELTS-reported overall band", () => {
    // 6.5 + 6.5 + 5.0 + 7.0 = 25 -> mean 6.25 -> reported 6.5
    expect(
      computeOverallBand({
        listening: 6.5,
        reading: 6.5,
        writing: 5,
        speaking: 7,
      }),
    ).toBe(6.5);

    // 6.5 + 6.5 + 7.5 + 6.5 = 27 -> mean 6.75 -> reported 7.0
    expect(
      computeOverallBand({
        listening: 6.5,
        reading: 6.5,
        writing: 7.5,
        speaking: 6.5,
      }),
    ).toBe(7);

    // All equal -> unchanged.
    expect(
      computeOverallBand({
        listening: 8,
        reading: 8,
        writing: 8,
        speaking: 8,
      }),
    ).toBe(8);
  });

  it("treats band 0 across the board as a real result, not as missing", () => {
    expect(
      computeOverallBand({
        listening: 0,
        reading: 0,
        writing: 0,
        speaking: 0,
      }),
    ).toBe(0);
  });
});

describe("formatBand", () => {
  it("always shows one decimal place", () => {
    expect(formatBand(7)).toBe("7.0");
    expect(formatBand(6.5)).toBe("6.5");
  });
});
