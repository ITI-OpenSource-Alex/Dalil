/**
 * Deriving something display-worthy from an email address.
 *
 * `CurrentUser` (app/types/profile.ts) carries no separate display name,
 * only an email — every place in the app that shows "who you are" (the
 * sidebar's avatar badge, the marketing navbar's account menu, Chat's
 * avatar, the Dashboard's welcome greeting) has to derive one from it. Each
 * of those had grown its own slightly different algorithm, so the same
 * email produced different initials in the sidebar than in the navbar. One
 * shared derivation, used everywhere, is what keeps that consistent.
 */

/**
 * Up to 2 uppercase initials for an avatar badge.
 *
 * Splits the local part on `.`/`_`/`-` and takes the first letter of the
 * first two segments (`jane.doe` -> "JD"), which reads better for the
 * common `firstname.lastname` shape than simply slicing the first two
 * characters (`jane.doe` -> "JA"). Falls back to the first two characters
 * when there's only one segment.
 */
export function emailInitials(email: string): string {
  const [local] = email.split("@");
  if (!local) return "?";
  const parts = local.split(/[._-]+/).filter(Boolean);
  const letters =
    parts.length > 1 ? `${parts[0][0]}${parts[1][0]}` : local.slice(0, 2);
  return letters.toUpperCase() || "?";
}

/** Turns "jane.doe97" into "Jane Doe" for a greeting -- same segmentation as
 *  emailInitials, extended into whole words instead of single letters. */
export function emailGreetingName(email: string): string {
  const [local] = email.split("@");
  if (!local) return email;
  const cleaned = local.replace(/[._-]+/g, " ").replace(/\d+/g, " ").trim();
  if (!cleaned) return email;
  return cleaned.replace(/\b\w/g, (c) => c.toUpperCase());
}
