/**
 * IELTS band arithmetic.
 *
 * The overall band is not the plain mean of the four section scores: IELTS
 * rounds the mean to the *nearest* half band, and a mean ending in .25 rounds
 * UP to the next half band while .75 rounds up to the next whole band. Working
 * that out by hand is exactly the sort of thing the onboarding wizard used to
 * ask candidates to do in a free-text box, which is both a chore and a
 * reliable source of wrong profile data.
 *
 * Reference: IELTS "How IELTS is scored" — a mean of 6.25 is reported as 6.5,
 * a mean of 6.75 as 7.0, a mean of 6.1 as 6.0.
 */

/** The 19 reportable band values, 0 through 9 in half-band steps. */
export const BAND_VALUES: number[] = Array.from(
  { length: 19 },
  (_, i) => i * 0.5,
);

/** True for a value that IELTS can actually report: 0-9 in 0.5 steps. */
export function isValidBand(value: number): boolean {
  return (
    Number.isFinite(value) && value >= 0 && value <= 9 && (value * 2) % 1 === 0
  );
}

/**
 * Parses a band typed as text. Returns null for anything unreportable, so
 * callers never have to distinguish "empty" from "NaN" from "9.3".
 */
export function parseBand(value: string): number | null {
  const trimmed = value.trim();
  if (!trimmed) return null;
  const num = Number(trimmed);
  return isValidBand(num) ? num : null;
}

/**
 * Rounds an arithmetic mean to the reported overall band.
 *
 * Math.round is deliberate rather than a floor/ceil pair: rounding
 * `mean * 2` to the nearest integer and halving is precisely the
 * "nearest half band, .25 rounds up" rule, because 6.25 * 2 = 12.5 rounds
 * to 13 -> 6.5, while 6.1 * 2 = 12.2 rounds to 12 -> 6.0.
 */
export function roundToBand(mean: number): number {
  return Math.round(mean * 2) / 2;
}

export interface SectionBands {
  listening: number | null;
  reading: number | null;
  writing: number | null;
  speaking: number | null;
}

/**
 * The overall band implied by four section scores, or null when any section is
 * still missing. Returning null rather than a partial average matters: a
 * half-filled form must not display a confident-looking band that will change
 * as soon as the next box is typed in.
 */
export function computeOverallBand(sections: SectionBands): number | null {
  const values = [
    sections.listening,
    sections.reading,
    sections.writing,
    sections.speaking,
  ];
  if (values.some((v) => v === null || !isValidBand(v))) return null;

  const total = (values as number[]).reduce((sum, v) => sum + v, 0);
  return roundToBand(total / 4);
}

/** "7.5" — bands are always shown to one decimal place, never "7". */
export function formatBand(value: number): string {
  return value.toFixed(1);
}

/**
 * The same one-decimal rendering, for a band that arrived over HTTP.
 *
 * `formatBand` takes the number its type says it takes. This takes whatever
 * the API actually sent, because that is a boundary this app does not own:
 * `ieltsScore` is a Postgres `numeric`, and node-postgres returns those as
 * strings unless the owning service converts them (it now does — see
 * services/user/src/common/database/numeric.transformer.ts). Calling
 * `.toFixed(1)` on the string crashed the profile page, and the declared type
 * `number | null` gave no warning because the lie started in the database
 * driver.
 *
 * Returns null for anything that is not a finite number, so callers render
 * "—" instead of "NaN" — which is also the honest answer for a band nobody
 * has entered yet.
 */
export function formatBandValue(value: unknown): string | null {
  if (value === null || value === undefined) return null;

  const band = typeof value === "number" ? value : Number(String(value).trim());
  // Number("") is 0, so an empty string would render as a band of 0.0 rather
  // than as "not answered".
  if (typeof value === "string" && value.trim() === "") return null;

  return Number.isFinite(band) ? band.toFixed(1) : null;
}

/**
 * A short, plain description of what a band means, used as inline guidance so
 * a candidate can sanity-check the number they just entered.
 */
export function bandDescriptor(value: number): string {
  if (value >= 8.5) return "Expert / very good user";
  if (value >= 7.5) return "Very good user";
  if (value >= 6.5) return "Competent to good user";
  if (value >= 5.5) return "Modest to competent user";
  if (value >= 4.5) return "Limited user";
  return "Extremely limited user";
}
