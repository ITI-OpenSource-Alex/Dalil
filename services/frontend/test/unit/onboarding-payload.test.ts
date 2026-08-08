import { describe, expect, it } from "vitest";
import { buildProfilePayload } from "@/app/onboarding/page";
import {
  EMPTY_ACADEMIC,
  EMPTY_LANGUAGE,
  EMPTY_TARGETS,
} from "@/components/onboarding/types";
import { STUDY_DESTINATIONS } from "@/lib/reference-data";
import { CATALOGUE_COUNTRIES } from "@/lib/reference-data";

describe("buildProfilePayload", () => {
  it("sends target countries as full names, matching RAG's country column", () => {
    // The regression this guards: the wizard used to persist short ids
    // ("us", "de", "eu"). RAG filters candidates with
    // `WHERE country = ANY($1::text[])` against a column holding 'Germany',
    // so a stated preference matched nothing at all — strictly worse than
    // stating none, because an absent filter widens the search.
    const payload = buildProfilePayload(EMPTY_ACADEMIC, EMPTY_LANGUAGE, {
      ...EMPTY_TARGETS,
      destinations: ["Germany", "Netherlands"],
    });

    expect(payload.targetCountries).toEqual(["Germany", "Netherlands"]);
    for (const country of payload.targetCountries ?? []) {
      expect(country).not.toMatch(/^[a-z]{2}$/);
    }
  });

  it("only offers destinations whose value is a full country name", () => {
    for (const destination of STUDY_DESTINATIONS) {
      expect(destination.name.length).toBeGreaterThan(2);
      expect(destination.name[0]).toBe(destination.name[0].toUpperCase());
    }
  });

  it("covers every catalogue country in the destination list", () => {
    const names = new Set(STUDY_DESTINATIONS.map((d) => d.name));
    for (const country of CATALOGUE_COUNTRIES) {
      expect(names.has(country)).toBe(true);
    }
  });

  it("omits the IELTS score when the candidate has not sat the exam", () => {
    const payload = buildProfilePayload(
      EMPTY_ACADEMIC,
      { ...EMPTY_LANGUAGE, hasTakenIelts: "no", targetOverallScore: "7.5" },
      EMPTY_TARGETS,
    );
    // A *target* band is an aspiration; writing it to ieltsScore would make
    // RAG's hard gate compare a wish against min_ielts.
    expect(payload.ieltsScore).toBeUndefined();
  });

  it("persists a computed overall band", () => {
    const payload = buildProfilePayload(
      EMPTY_ACADEMIC,
      { ...EMPTY_LANGUAGE, hasTakenIelts: "yes", overallScore: "6.5" },
      EMPTY_TARGETS,
    );
    expect(payload.ieltsScore).toBe(6.5);
  });

  it("includes IELTS sub-scores alongside overall when the exam was taken", () => {
    const payload = buildProfilePayload(
      EMPTY_ACADEMIC,
      {
        ...EMPTY_LANGUAGE,
        hasTakenIelts: "yes",
        listeningScore: "7.5",
        readingScore: "7.0",
        writingScore: "6.5",
        speakingScore: "7.0",
        overallScore: "7.0",
      },
      EMPTY_TARGETS,
    );
    expect(payload.ieltsListening).toBe(7.5);
    expect(payload.ieltsReading).toBe(7.0);
    expect(payload.ieltsWriting).toBe(6.5);
    expect(payload.ieltsSpeaking).toBe(7.0);
    expect(payload.ieltsScore).toBe(7.0);
  });

  it("refuses an unreportable band rather than persisting it", () => {
    // 6.4 is not a band. Letting it through would silently mis-gate every
    // programme whose min_ielts sits between 6.0 and 6.5.
    const payload = buildProfilePayload(
      EMPTY_ACADEMIC,
      { ...EMPTY_LANGUAGE, hasTakenIelts: "yes", overallScore: "6.4" },
      EMPTY_TARGETS,
    );
    expect(payload.ieltsScore).toBeUndefined();
  });

  it("sends the GPA scale alongside the GPA, never on its own", () => {
    const withGpa = buildProfilePayload(
      { ...EMPTY_ACADEMIC, gpa: "85", gpaScale: "100" },
      EMPTY_LANGUAGE,
      EMPTY_TARGETS,
    );
    expect(withGpa.gpa).toBe(85);
    expect(withGpa.gpaScale).toBe("100");

    const withoutGpa = buildProfilePayload(
      { ...EMPTY_ACADEMIC, gpaScale: "100" },
      EMPTY_LANGUAGE,
      EMPTY_TARGETS,
    );
    expect(withoutGpa.gpa).toBeUndefined();
    expect(withoutGpa.gpaScale).toBeUndefined();
  });

  it("produces an empty payload for a wholly skipped wizard", () => {
    // The page skips the network call entirely on an empty payload rather
    // than issuing a PUT with no body.
    const payload = buildProfilePayload(
      EMPTY_ACADEMIC,
      EMPTY_LANGUAGE,
      EMPTY_TARGETS,
    );
    expect(Object.keys(payload)).toEqual([]);
  });
});
