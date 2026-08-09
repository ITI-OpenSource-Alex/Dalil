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
  it("is strong when the composite fit score is at least 90", () => {
    expect(matchTone(prog(90))).toBe("strong");
    expect(matchTone(prog(89))).toBe("possible");
  });
  it("is possible for 70–89", () => {
    expect(matchTone(prog(70))).toBe("possible");
  });
  it("is stretch below 70", () => {
    expect(matchTone(prog(69.9))).toBe("stretch");
  });
  it("labels limited academic evidence instead of presenting false precision", () => {
    const program = prog(85);
    program.result.score_breakdown = {
      eligibility_points: 40,
      requirement_headroom_points: null,
      subject_points: 35,
      destination_points: 10,
      headroom_dimensions_evaluated: 0,
      confidence: "limited",
      total: 85,
    };
    expect(matchTone(program)).toBe("unknown");
  });
});
