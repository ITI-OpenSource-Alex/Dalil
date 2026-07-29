// Frontend-local answer comparison helpers.
//
// These are NOT a duplicate of backend grading — the backend
// (services/exam/app/services/grading_service.py:_normalize_strict) is the
// sole authority on whether an answer is actually correct, and already
// does its own whitespace-collapsing + case-insensitive comparison
// (uppercasing, not lowercasing) before scoring. This file exists only for
// frontend-local concerns — e.g. comparing what a user typed against a
// previous value.

/** Trims whitespace and lowercases both sides before comparing. */
export function compareFillInBlankAnswers(
  a: string | null | undefined,
  b: string | null | undefined,
): boolean {
  return normalizeFillInBlankAnswer(a) === normalizeFillInBlankAnswer(b);
}

export function normalizeFillInBlankAnswer(
  value: string | null | undefined,
): string {
  return (value ?? "").trim().toLowerCase();
}
