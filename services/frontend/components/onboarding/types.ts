export interface AcademicData {
  degree: string;
  major: string;
  university: string;
  gradYear: string;
  gpa: string;
  gpaScale: "4.0" | "100";
  ects: string;
}

export interface LanguageData {
  hasTakenIelts: "yes" | "no" | "";
  listeningScore: string;
  readingScore: string;
  writingScore: string;
  speakingScore: string;
  /**
   * The reported overall band. Computed from the four sections by
   * lib/ielts.ts rather than typed, but still stored as a string because
   * `overrideOverall` lets a candidate enter the band printed on their test
   * report when it disagrees with the naive mean (a rounding edge, or a
   * remark). Persisted to `ieltsScore`.
   */
  overallScore: string;
  /** True once the candidate has taken manual control of the overall band. */
  overrideOverall: boolean;
  planningToTake: "yes" | "no" | "";
  targetOverallScore: string;
  targetExamDate: string;
}

export interface TargetsData {
  /**
   * Full country NAMES ("Germany"), not short ids ("de").
   *
   * These are persisted verbatim to `targetCountries` and RAG filters
   * candidate programmes with `WHERE country = ANY($1::text[])` against a
   * column holding full names. The wizard used to store DESTINATION_COUNTRIES
   * ids here, so any candidate who named a target country matched *nothing* --
   * a stated preference made the results strictly worse than leaving it blank,
   * because an absent filter widens the search while a wrong one empties it.
   * See lib/reference-data.ts.
   */
  destinations: string[];
  targetDegree: string;
  targetMajor: string;
  targetIntake: string;
}

export const EMPTY_ACADEMIC: AcademicData = {
  degree: "",
  major: "",
  university: "",
  gradYear: "",
  gpa: "",
  gpaScale: "4.0",
  ects: "",
};

export const EMPTY_LANGUAGE: LanguageData = {
  hasTakenIelts: "",
  listeningScore: "",
  readingScore: "",
  writingScore: "",
  speakingScore: "",
  overallScore: "",
  overrideOverall: false,
  planningToTake: "",
  targetOverallScore: "",
  targetExamDate: "",
};

export const EMPTY_TARGETS: TargetsData = {
  destinations: [],
  targetDegree: "",
  targetMajor: "",
  targetIntake: "",
};

/**
 * Draft persistence.
 *
 * The wizard's four steps live in component state while the step number lives
 * in the URL, so a refresh -- or following the Complete Profile link from the
 * sidebar in a new tab -- restored the step and lost every answer. sessionStorage
 * rather than localStorage: a draft profile is not something to leave lying
 * around on a shared machine indefinitely, and it is cleared on successful
 * submit regardless.
 */
const DRAFT_KEY = "goa.onboarding.draft";

export interface OnboardingDraft {
  academic: AcademicData;
  language: LanguageData;
  targets: TargetsData;
}

export const EMPTY_DRAFT: OnboardingDraft = {
  academic: EMPTY_ACADEMIC,
  language: EMPTY_LANGUAGE,
  targets: EMPTY_TARGETS,
};

export function loadDraft(): OnboardingDraft {
  if (typeof window === "undefined") return EMPTY_DRAFT;
  try {
    const raw = window.sessionStorage.getItem(DRAFT_KEY);
    if (!raw) return EMPTY_DRAFT;
    const parsed = JSON.parse(raw) as Partial<OnboardingDraft>;
    // Spread over the empty shapes so a draft written by an older build --
    // missing `overrideOverall`, say -- restores as a valid object rather than
    // one with undefined fields that later render as uncontrolled inputs.
    return {
      academic: { ...EMPTY_ACADEMIC, ...parsed.academic },
      language: { ...EMPTY_LANGUAGE, ...parsed.language },
      targets: { ...EMPTY_TARGETS, ...parsed.targets },
    };
  } catch {
    return EMPTY_DRAFT;
  }
}

export function saveDraft(draft: OnboardingDraft): void {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.setItem(DRAFT_KEY, JSON.stringify(draft));
  } catch {
    // A full or unavailable sessionStorage (private mode, quota) must not take
    // the wizard down with it -- the draft is a convenience, not the feature.
  }
}

export function clearDraft(): void {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.removeItem(DRAFT_KEY);
  } catch {
    /* see saveDraft */
  }
}
