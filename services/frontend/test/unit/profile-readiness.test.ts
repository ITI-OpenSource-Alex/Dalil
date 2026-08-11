import { describe, expect, it } from "vitest";
import { MATCH_FIELDS, matchReadiness } from "@/lib/profile-readiness";
import type { UserProfileDetail } from "@/app/types/profile";

const EMPTY: UserProfileDetail = {
  userId: "user-1",
  degreeLevel: null,
  gpa: null,
  ieltsScore: null,
  ieltsListening: null,
  ieltsReading: null,
  ieltsWriting: null,
  ieltsSpeaking: null,
  targetCountries: [],
  fieldOfStudy: null,
  targetFieldOfStudy: null,
  ects: null,
  workExperienceYears: 0,
  extracurricularsScore: 0,
  gpaScale: "4.0",
};

const FULL: UserProfileDetail = {
  ...EMPTY,
  degreeLevel: "Bachelors",
  gpa: 3.2,
  ects: 180,
  ieltsScore: 7,
  fieldOfStudy: "Computer Science",
  targetFieldOfStudy: "Software Engineering",
  targetCountries: ["Germany"],
};

describe("matchReadiness", () => {
  it("counts nothing and lists every field for a null profile", () => {
    const readiness = matchReadiness(null);
    expect(readiness.filled).toBe(0);
    expect(readiness.total).toBe(MATCH_FIELDS.length);
    expect(readiness.ready).toBe(false);
    expect(readiness.missing.map((f) => f.key)).toEqual(
      MATCH_FIELDS.map((f) => f.key),
    );
  });

  it("is ready once every field matching reads is present", () => {
    const readiness = matchReadiness(FULL);
    expect(readiness.filled).toBe(readiness.total);
    expect(readiness.missing).toEqual([]);
    expect(readiness.ready).toBe(true);
  });

  it("counts a zero GPA as filled rather than missing", () => {
    const readiness = matchReadiness({ ...FULL, gpa: 0 });
    expect(readiness.missing.map((f) => f.key)).not.toContain("gpa");
  });

  it("accepts fieldOfStudy as the intended field when targetFieldOfStudy is unset", () => {
    const readiness = matchReadiness({ ...FULL, targetFieldOfStudy: null });
    expect(readiness.missing.map((f) => f.key)).not.toContain(
      "targetFieldOfStudy",
    );
  });

  it("treats an empty country list as missing", () => {
    const readiness = matchReadiness({ ...FULL, targetCountries: [] });
    expect(readiness.missing.map((f) => f.key)).toContain("targetCountries");
    expect(readiness.ready).toBe(false);
  });

  it("survives a profile whose targetCountries never arrived as an array", () => {
    const broken = {
      ...FULL,
      targetCountries: undefined,
    } as unknown as UserProfileDetail;
    expect(() => matchReadiness(broken)).not.toThrow();
    expect(matchReadiness(broken).ready).toBe(false);
  });

  it("excludes fields that can never be missing", () => {
    const keys = MATCH_FIELDS.map((f) => f.key) as string[];
    expect(keys).not.toContain("workExperienceYears");
    expect(keys).not.toContain("extracurricularsScore");
  });

  it("points every field at a form section anchor", () => {
    for (const field of MATCH_FIELDS) {
      expect(field.section).toMatch(/^profile-section-/);
      expect(field.label.length).toBeGreaterThan(0);
    }
  });
});
