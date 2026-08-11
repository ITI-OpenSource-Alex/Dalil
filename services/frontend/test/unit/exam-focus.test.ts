import { describe, expect, it } from "vitest";
import { isExamFocusPath } from "@/lib/exam-focus";

describe("isExamFocusPath", () => {
  it("returns true for /exam/shell", () => {
    expect(isExamFocusPath("/exam/shell")).toBe(true);
  });

  it("returns true for /exam/shell with a trailing slash", () => {
    expect(isExamFocusPath("/exam/shell/")).toBe(true);
  });

  it("ignores that real navigations may carry a query (pathname only)", () => {
    // usePathname() does not include search; callers pass pathname only.
    expect(isExamFocusPath("/exam/shell")).toBe(true);
  });

  it("returns false for exam hub and results", () => {
    expect(isExamFocusPath("/exam")).toBe(false);
    expect(isExamFocusPath("/exam/")).toBe(false);
    expect(isExamFocusPath("/exam/results")).toBe(false);
  });

  it("returns false for other app routes and lookalikes", () => {
    expect(isExamFocusPath("/chat")).toBe(false);
    expect(isExamFocusPath("/exam/shell/extra")).toBe(false);
    expect(isExamFocusPath("/exam/shellfish")).toBe(false);
    expect(isExamFocusPath("")).toBe(false);
  });
});
