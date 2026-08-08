import { describe, expect, it } from "vitest";
import { matchTone, type MatchedProgram } from "@/lib/opportunities-api";

function prog(score: number, blocked_by: string | null = null): MatchedProgram {
  return {
    programId: "1",
    programName: "MSc",
    university: "U",
    country: "DE",
    deadline: null,
    result: { score, blocked_by },
  };
}

describe("matchTone", () => {
  it("marks blocked regardless of score", () => {
    expect(matchTone(prog(99, "ielts"))).toBe("blocked");
  });
  it("is strong when score > 80", () => {
    expect(matchTone(prog(81))).toBe("strong");
    expect(matchTone(prog(80))).toBe("possible");
  });
  it("is possible for 60–80", () => {
    expect(matchTone(prog(60))).toBe("possible");
  });
  it("is stretch below 60", () => {
    expect(matchTone(prog(59.9))).toBe("stretch");
  });
});
