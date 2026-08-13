import { describe, it, expect } from "vitest";
import { normalizeCurrentUser } from "@/lib/profile-api";
import { isProfileComplete } from "@/app/types/profile";

/**
 * GET /api/profile serves `gpa` and `ieltsScore` from PostgreSQL `numeric`
 * columns, which node-postgres returns as strings. The response was handed
 * straight out as a `CurrentUser` on the strength of the declared return type,
 * so `"7.5"` satisfied both the compiler and the profile page's `!= null`
 * guard, then blew up on `.toFixed(1)`.
 *
 * The User service entity now converts on read; these cover the client half,
 * which is what holds if the shape regresses upstream again.
 */
const rawUser = (profile: Record<string, unknown> | null) => ({
  id: "u1",
  email: "a@b.c",
  subscriptionTier: "free",
  isVerified: true,
  profile,
});

describe("normalizeCurrentUser", () => {
  it("converts numeric-as-string fields into real numbers", () => {
    const { profile } = normalizeCurrentUser(
      rawUser({ ieltsScore: "7.5", gpa: "3.85", ects: "180" }),
    );

    expect(profile?.ieltsScore).toBe(7.5);
    expect(profile?.gpa).toBe(3.85);
    expect(profile?.ects).toBe(180);
  });

  it("produces a value .toFixed() can be called on — the exact crash", () => {
    const { profile } = normalizeCurrentUser(rawUser({ ieltsScore: "7.5" }));

    expect(() => profile!.ieltsScore!.toFixed(1)).not.toThrow();
    expect(profile!.ieltsScore!.toFixed(1)).toBe("7.5");
  });

  it("leaves an absent IELTS score null so the page renders its empty state", () => {
    // The other half of the bug report: the page must render for users with
    // and without a score. null takes the `: null` branch; 0 would print
    // "0.0" as though the user had actually sat the exam and failed it.
    const { profile } = normalizeCurrentUser(
      rawUser({ ieltsScore: null, gpa: null, ects: null }),
    );

    expect(profile?.ieltsScore).toBeNull();
    expect(profile?.gpa).toBeNull();
    expect(profile?.ects).toBeNull();
  });

  it("treats an empty string as absent rather than as 0", () => {
    const { profile } = normalizeCurrentUser(rawUser({ ieltsScore: "" }));
    expect(profile?.ieltsScore).toBeNull();
  });

  it("keeps a genuine zero, which is distinct from absent", () => {
    const { profile } = normalizeCurrentUser(
      rawUser({ ieltsScore: "0.0", extracurricularsScore: 0 }),
    );
    expect(profile?.ieltsScore).toBe(0);
    expect(profile?.extracurricularsScore).toBe(0);
  });

  it("falls back to 0 for the NOT NULL counters the model declares required", () => {
    const { profile } = normalizeCurrentUser(rawUser({}));
    expect(profile?.workExperienceYears).toBe(0);
    expect(profile?.extracurricularsScore).toBe(0);
  });

  it("defends targetCountries so isProfileComplete cannot throw on .length", () => {
    const { profile } = normalizeCurrentUser(
      rawUser({ targetCountries: null, ieltsScore: null }),
    );

    expect(profile?.targetCountries).toEqual([]);
    expect(() => isProfileComplete(profile)).not.toThrow();
  });

  it("passes a null profile through untouched", () => {
    expect(normalizeCurrentUser(rawUser(null)).profile).toBeNull();
  });

  it("keeps isProfileComplete honest once values are coerced", () => {
    const complete = normalizeCurrentUser(rawUser({ ieltsScore: "7.5" }));
    const empty = normalizeCurrentUser(
      rawUser({ ieltsScore: null, gpa: null, degreeLevel: null, fieldOfStudy: null }),
    );

    expect(isProfileComplete(complete.profile)).toBe(true);
    expect(isProfileComplete(empty.profile)).toBe(false);
  });
});
