import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { OpportunityCard } from "@/components/opportunities/opportunity-card";
import type { MatchedProgram } from "@/lib/opportunities-api";

const longProgram: MatchedProgram = {
  programId: "programme-1",
  programName: "Information Engineering and Computer Science",
  university: "South Westphalia University of Applied Sciences",
  country: "Germany",
  deadline: null,
  sourceUrl: "https://example.edu/programme",
  dataSource: "scraped",
  result: {
    score: 99,
    requirements_evaluated: 3,
    requirements_met: 3,
    blocked_by: null,
    score_breakdown: {
      eligibility_points: 40,
      requirement_headroom_points: 14,
      subject_points: 35,
      destination_points: 10,
      headroom_dimensions_evaluated: 3,
      confidence: "standard",
      subject_relevance: 1,
      total: 99,
    },
  },
};

describe("OpportunityCard constrained layout", () => {
  it("keeps long identity and score text inside a fixed-width grid cell", () => {
    render(<OpportunityCard program={longProgram} />);

    const heading = screen.getByRole("heading", {
      name: longProgram.programName,
    });
    expect(heading).toHaveClass("truncate");
    expect(heading).toHaveAttribute("title", longProgram.programName);

    const university = screen.getByText(longProgram.university);
    expect(university).toHaveClass("truncate");
    expect(university).toHaveAttribute("title", longProgram.university);

    const score = screen.getByText(/Score: 40 eligibility/);
    expect(score).toHaveClass("truncate");
    expect(score.getAttribute("title")).toContain("destination fit");
  });
});
