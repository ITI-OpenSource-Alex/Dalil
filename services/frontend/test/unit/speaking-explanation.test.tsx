import { describe, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";

import { SpeakingExplanation } from "@/components/practice/speaking-explanation";
import type {
  ExplanationMeta,
  Renderable,
} from "@/lib/speaking-explanation";
import {
  scoreSemanticsCopy,
  unavailableCopy,
  withheldNotice,
} from "@/lib/speaking-explanation";

/**
 * SPEAK-EVAL-008 acceptance, at the surface:
 *
 *  - invalid explanations are never silently shown;
 *  - partial results and pronunciation limitations are explicit;
 *  - accessibility tests cover evidence controls and status updates.
 *
 * The component renders what the server decided may be shown. So these tests
 * check the *presentation* obligations — that a withheld count reaches the
 * screen, that an unassessed criterion never shows a number, and that the
 * band's qualifier cannot be separated from the band.
 */

const baseRenderable: Renderable = {
  EvaluationID: "eval-1",
  Mode: "practice",
  Status: "complete",
  Band: 6.5,
  UnroundedMean: 6.375,
  ScoreSemantics: "estimated_ielts_practice_band",
  RubricID: "ielts-speaking-public",
  RubricVersion: "2023-06",
  Criteria: [
    {
      CriterionID: "fluency_coherence",
      Status: "scored",
      Band: 6.5,
      Claims: [
        {
          Kind: "rubric",
          Text: "Is willing to speak at length, though may lose coherence at times.",
          DescriptorID: "fc.6",
          DescriptorBand: 6,
          Polarity: "supports",
        },
        {
          Kind: "rubric",
          Text: "Speaks at length without noticeable effort or loss of coherence.",
          DescriptorID: "fc.7",
          DescriptorBand: 7,
          Polarity: "caps_below",
        },
        {
          Kind: "evidence",
          Text: "Hesitation before a content word.",
          Quote: "it was a trip to a small",
          CharStart: 62,
          CharEnd: 86,
        },
        { Kind: "summary", Text: "You spoke at length with clear organisation." },
        { Kind: "action", Text: "Record the same answer again." },
      ],
    },
  ],
};

function withCriteria(criteria: Renderable["Criteria"]): Renderable {
  return { ...baseRenderable, Criteria: criteria };
}

describe("SpeakingExplanation", () => {
  it("renders each resolved claim kind under its own heading", () => {
    render(<SpeakingExplanation renderable={baseRenderable} />);

    expect(screen.getByText(/Against the official descriptors/i)).toBeInTheDocument();
    expect(screen.getByText(/From your answer/i)).toBeInTheDocument();
    expect(screen.getByText(/What to practise/i)).toBeInTheDocument();
    expect(
      screen.getByText(/You spoke at length with clear organisation/i),
    ).toBeInTheDocument();
  });

  it("shows caps_below as what would take the candidate higher", () => {
    // The distinction that makes an explanation actionable: "why not a 7" is
    // more useful than "why a 6".
    render(<SpeakingExplanation renderable={baseRenderable} />);

    expect(screen.getByText(/What would take you higher/i)).toBeInTheDocument();
    expect(screen.getByText(/What you did/i)).toBeInTheDocument();
  });

  it("never renders a number for an unassessed criterion", () => {
    // Band 0.0 is a real IELTS value. A dash or a zero here would be read as one.
    render(
      <SpeakingExplanation
        renderable={withCriteria([
          {
            CriterionID: "pronunciation",
            Status: "unavailable",
            UnavailableReason: "insufficient_evidence",
          },
        ])}
      />,
    );

    const card = screen.getByRole("article", { name: /Pronunciation/i });
    expect(within(card).getByText(/Not assessed/i)).toBeInTheDocument();
    expect(within(card).queryByText(/^0\.0$/)).not.toBeInTheDocument();
    expect(
      within(card).getByText(/not enough in this recording/i),
    ).toBeInTheDocument();
  });

  it("states when observations were withheld rather than showing fewer", () => {
    render(
      <SpeakingExplanation
        renderable={withCriteria([
          {
            CriterionID: "lexical_resource",
            Status: "scored",
            Band: 6,
            Claims: [{ Kind: "rubric", Text: "…", DescriptorID: "lr.6", Polarity: "supports" }],
            Withheld: [
              { Kind: "evidence", Reason: "quote_not_found_at_offsets", Detail: "x" },
              { Kind: "evidence", Reason: "measurement_not_in_provenance", Detail: "y" },
            ],
          },
        ])}
      />,
    );

    const notice = screen.getByText(/2 further observations could not be verified/i);
    expect(notice).toBeInTheDocument();
    // Announced, so a screen reader learns the explanation is incomplete.
    expect(notice).toHaveAttribute("role", "status");
  });

  it("explains an absent overall band instead of rendering a blank", () => {
    render(
      <SpeakingExplanation
        renderable={{
          ...baseRenderable,
          Band: undefined,
          Status: "partial",
          BandWithheldReason:
            "An overall band needs at least 3 of the 4 criteria. 2 completed, so no overall band was calculated.",
        }}
      />,
    );

    const status = screen.getByRole("status");
    expect(status).toHaveTextContent(/at least 3 of the 4 criteria/i);
  });

  it("keeps the practice-band qualifier attached to the score", () => {
    // A band shown without this implies a certified assessment.
    render(<SpeakingExplanation renderable={baseRenderable} />);

    expect(
      screen.getByText(/Not an official IELTS score/i),
    ).toBeInTheDocument();
  });

  it("shows a criterion's limitations under their own heading", () => {
    render(
      <SpeakingExplanation
        renderable={withCriteria([
          {
            CriterionID: "pronunciation",
            Status: "scored",
            Band: 6.5,
            Claims: [{ Kind: "rubric", Text: "…", DescriptorID: "pr.6", Polarity: "supports" }],
            Limitations: [
              "This score reflects how clearly your speech was recognised. It does not assess individual sounds, word stress or intonation.",
            ],
          },
        ])}
      />,
    );

    expect(screen.getByText(/What this does not cover/i)).toBeInTheDocument();
    expect(screen.getByText(/does not assess individual sounds/i)).toBeInTheDocument();
  });

  it("does not offer a transcript position when the surface has no transcript", () => {
    // A control that cannot work is worse than no control.
    const { rerender } = render(
      <SpeakingExplanation renderable={baseRenderable} />,
    );
    expect(screen.queryByText(/at character 62/i)).not.toBeInTheDocument();

    rerender(
      <SpeakingExplanation
        renderable={baseRenderable}
        transcript={"x".repeat(200)}
      />,
    );
    expect(screen.getByText(/at character 62/i)).toBeInTheDocument();
  });

  it("gives every criterion an accessible name and a labelled region", () => {
    render(<SpeakingExplanation renderable={baseRenderable} />);

    expect(
      screen.getByRole("region", { name: /How this was assessed/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("article", { name: /Fluency and Coherence/i }),
    ).toBeInTheDocument();
  });

  it("renders provenance without which two explanations are not comparable", () => {
    const meta: ExplanationMeta = {
      rubric_id: "ielts-speaking-public",
      rubric_version: "2023-06",
      scorer_version: "speaking@abc123",
      llm_model: "claude-opus-4-8",
      claim_count: 5,
      withheld_count: 2,
    };

    render(<SpeakingExplanation renderable={baseRenderable} meta={meta} />);

    expect(screen.getByText(/speaking@abc123/)).toBeInTheDocument();
    expect(screen.getByText(/claude-opus-4-8/)).toBeInTheDocument();
    expect(screen.getByText(/5 shown/)).toBeInTheDocument();
    expect(screen.getByText(/2 unverified/)).toBeInTheDocument();
    // The unrounded mean, so the arithmetic is visible rather than trusted.
    expect(screen.getByText(/6\.38/)).toBeInTheDocument();
  });
});

describe("explanation copy", () => {
  it("distinguishes failure reasons a student can act on differently", () => {
    // A deadline is worth retrying; a provider error is not the student's
    // problem; insufficient evidence means the recording itself was the limit.
    expect(unavailableCopy("deadline_exceeded")).toMatch(/trying again/i);
    expect(unavailableCopy("provider_error")).toMatch(/our side/i);
    expect(unavailableCopy("insufficient_evidence")).toMatch(/not enough/i);
    expect(unavailableCopy(undefined)).toMatch(/not assessed/i);

    const all = [
      unavailableCopy("deadline_exceeded"),
      unavailableCopy("provider_error"),
      unavailableCopy("insufficient_evidence"),
    ];
    expect(new Set(all).size).toBe(3);
  });

  it("returns no withheld notice when nothing was withheld", () => {
    expect(withheldNotice(0)).toBeNull();
    expect(withheldNotice(1)).toMatch(/1 further observation could not/i);
    expect(withheldNotice(3)).toMatch(/3 further observations/i);
  });

  it("never describes an estimate as an official score", () => {
    const copy = scoreSemanticsCopy("estimated_ielts_practice_band");
    expect(copy).toMatch(/not an official/i);
  });
});
