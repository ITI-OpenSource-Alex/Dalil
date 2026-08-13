import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import {
  READING_SPLIT_DEFAULT,
  READING_SPLIT_MAX,
  READING_SPLIT_MIN,
  READING_SPLIT_STORAGE_KEY,
  clampReadingSplitPercent,
  loadReadingSplitPercent,
  parseReadingSplitPercent,
  percentFromClientX,
  saveReadingSplitPercent,
} from "@/lib/reading-split";

describe("clampReadingSplitPercent", () => {
  it("clamps to the allowed range", () => {
    expect(clampReadingSplitPercent(10)).toBe(READING_SPLIT_MIN);
    expect(clampReadingSplitPercent(90)).toBe(READING_SPLIT_MAX);
    expect(clampReadingSplitPercent(55.4)).toBe(55);
  });

  it("falls back for non-finite values", () => {
    expect(clampReadingSplitPercent(Number.NaN)).toBe(READING_SPLIT_DEFAULT);
  });
});

describe("parseReadingSplitPercent", () => {
  it("uses the default for empty input", () => {
    expect(parseReadingSplitPercent(null)).toBe(READING_SPLIT_DEFAULT);
    expect(parseReadingSplitPercent("")).toBe(READING_SPLIT_DEFAULT);
  });

  it("parses and clamps stored strings", () => {
    expect(parseReadingSplitPercent("62")).toBe(62);
    expect(parseReadingSplitPercent("12")).toBe(READING_SPLIT_MIN);
  });
});

describe("percentFromClientX", () => {
  it("maps pointer position to a percent of the container", () => {
    expect(percentFromClientX(158, 100, 100)).toBe(58);
    expect(percentFromClientX(50, 100, 100)).toBe(READING_SPLIT_MIN);
  });
});

describe("load/saveReadingSplitPercent", () => {
  const store = new Map<string, string>();

  beforeEach(() => {
    store.clear();
    vi.stubGlobal("localStorage", {
      getItem: (key: string) => store.get(key) ?? null,
      setItem: (key: string, value: string) => {
        store.set(key, value);
      },
      removeItem: (key: string) => {
        store.delete(key);
      },
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("persists and reloads the clamped percent", () => {
    saveReadingSplitPercent(61);
    expect(store.get(READING_SPLIT_STORAGE_KEY)).toBe("61");
    expect(loadReadingSplitPercent()).toBe(61);
  });

  it("returns the default when nothing is stored", () => {
    expect(loadReadingSplitPercent()).toBe(READING_SPLIT_DEFAULT);
  });
});
