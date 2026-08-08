import { ValueTransformer } from 'typeorm';

/**
 * Makes a `decimal`/`numeric` column actually deliver the `number` its entity
 * property is declared as.
 *
 * node-postgres returns PostgreSQL `numeric` as a *string*, deliberately: the
 * type is arbitrary-precision and an IEEE double cannot represent every value
 * it can hold, so the driver refuses to lose precision silently. TypeORM does
 * not paper over that, which leaves `gpa: number` and `ieltsScore: number` in
 * UserProfile lying about their own runtime type — the entity, the controller's
 * JSON, the SQS event payload and the frontend's `number | null` model all
 * agreed on `number`, and every one of them was handed `"7.5"`.
 *
 * That mismatch is invisible until something calls a number-only method on it:
 * `ieltsScore.toFixed(1)` on the profile page threw "toFixed is not a function",
 * while `${gpa} / ${gpaScale}` next to it rendered fine because template
 * interpolation is happy to take a string. A per-render `Number(...)` would fix
 * one call site and leave the contract still wrong for the next one.
 *
 * Converting on read is safe for these two columns specifically: both are small
 * fixed-scale values (GPA 3.85, IELTS 7.5) that a double represents exactly
 * enough for display and comparison. Do not reuse this for money or any column
 * where full precision is the reason `numeric` was chosen.
 */
export const numericTransformer: ValueTransformer = {
  // Written back unchanged — the driver serialises a JS number into `numeric`
  // correctly, and re-stringifying here would only add a rounding step.
  to: (value: number | null | undefined) => value ?? null,

  from: (value: string | null | undefined): number | null => {
    if (value === null || value === undefined) return null;
    const parsed = Number(value);
    // A NULL column is the only legitimate "no value"; anything unparseable is
    // a corrupt row, and returning NaN would propagate a silent wrong number
    // into scoring rather than an absent one.
    return Number.isFinite(parsed) ? parsed : null;
  },
};
