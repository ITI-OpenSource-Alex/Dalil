import type { UserProfileDetail } from "@/app/types/profile";

/**
 * How ready this profile is for programme matching.
 *
 * The field list is taken from the matcher, not from what the form happens to
 * collect: services/rag/app/services/gates.py hard-gates on ects, degreeLevel,
 * ieltsScore and gpa (with gpaScale), and services/rag/app/services/scoring.py
 * ranks on targetFieldOfStudy (falling back to fieldOfStudy) and
 * targetCountries. A meter that counted anything else would promise the user
 * an improvement in matching that could not happen.
 *
 * workExperienceYears and extracurricularsScore are deliberately absent: both
 * are non-nullable numbers defaulting to 0, so they are never "missing", and
 * counting them would make the meter unreachable-by-design.
 *
 * This is a different question from isProfileComplete() in
 * app/types/profile.ts, which asks "has this user started their profile at
 * all" and drives the post-login redirect. Keep the two separate.
 */

export type ProfileSectionId =
  | "profile-section-academic"
  | "profile-section-ielts"
  | "profile-section-destinations";

export type MatchFieldKey =
  | "degreeLevel"
  | "gpa"
  | "ects"
  | "ieltsScore"
  | "targetFieldOfStudy"
  | "targetCountries";

export interface MatchField {
  key: MatchFieldKey;
  label: string;
  /** Form section that owns this field, for "fix it" deep links. */
  section: ProfileSectionId;
}

export const MATCH_FIELDS: readonly MatchField[] = [
  {
    key: "degreeLevel",
    label: "Degree level",
    section: "profile-section-academic",
  },
  { key: "gpa", label: "GPA", section: "profile-section-academic" },
  { key: "ects", label: "ECTS credits", section: "profile-section-academic" },
  {
    key: "ieltsScore",
    label: "IELTS overall band",
    section: "profile-section-ielts",
  },
  {
    key: "targetFieldOfStudy",
    label: "Intended field",
    section: "profile-section-destinations",
  },
  {
    key: "targetCountries",
    label: "Target countries",
    section: "profile-section-destinations",
  },
];

export interface MatchReadiness {
  filled: number;
  total: number;
  missing: MatchField[];
  ready: boolean;
}

function hasText(value: string | null | undefined): boolean {
  return typeof value === "string" && value.trim().length > 0;
}

function isFilled(profile: UserProfileDetail, field: MatchField): boolean {
  switch (field.key) {
    case "degreeLevel":
      return hasText(profile.degreeLevel);
    case "targetFieldOfStudy":
      return (
        hasText(profile.targetFieldOfStudy) || hasText(profile.fieldOfStudy)
      );
    case "targetCountries":
      return (
        Array.isArray(profile.targetCountries) &&
        profile.targetCountries.length > 0
      );
    case "gpa":
      return profile.gpa !== null && profile.gpa !== undefined;
    case "ects":
      return profile.ects !== null && profile.ects !== undefined;
    case "ieltsScore":
      return profile.ieltsScore !== null && profile.ieltsScore !== undefined;
  }
}

export function matchReadiness(
  profile: UserProfileDetail | null,
): MatchReadiness {
  const total = MATCH_FIELDS.length;
  if (!profile) {
    return { filled: 0, total, missing: [...MATCH_FIELDS], ready: false };
  }
  const missing = MATCH_FIELDS.filter((field) => !isFilled(profile, field));
  return {
    filled: total - missing.length,
    total,
    missing,
    ready: missing.length === 0,
  };
}
