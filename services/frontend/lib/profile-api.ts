import type { CurrentUser, UserProfileDetail } from "@/app/types/profile";
import { dedupe } from "@/lib/request-dedupe";

// Reached through the Gateway, not the User service directly — same reason as
// exam-api.ts/writing-api.ts (BUG-046): calling a service directly means shipping
// its internal key to the browser. GET /api/profile (services/gateway/handlers/
// profile.go) resolves the caller's id from the JWT itself, so no id is passed here.
const API_BASE = `${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8080"}/api`;

const fetchOptions: RequestInit = { credentials: "include" };

/** GET /api/profile — the authenticated user's own account + profile (BUG-047).
 *
 * Deduped: the sidebar and (as of the Dashboard) two of its widgets each call
 * this independently, and on first mount all three fire before any of them
 * has a response -- see lib/request-dedupe.ts.
 */
export async function getMyProfile(): Promise<CurrentUser> {
  return dedupe(`GET ${API_BASE}/profile`, async () => {
    const response = await fetch(`${API_BASE}/profile`, fetchOptions);
    if (!response.ok) {
      const message = await response.text().catch(() => "");
      throw new Error(message || `Request failed with status ${response.status}`);
    }
    return normalizeCurrentUser(await response.json());
  });
}

/**
 * Coerces the numeric profile fields before the response is handed out as a
 * `CurrentUser`.
 *
 * `gpa` and `ieltsScore` are PostgreSQL `numeric` columns. The User service now
 * converts them on read (its UserProfile entity carries a value transformer),
 * but this function is the boundary where untrusted JSON first claims to be
 * `UserProfileDetail`, and until now it made that claim by assertion alone —
 * `response.json()` returned `any` and the declared return type did the rest.
 * That is how `"7.5"` reached `ieltsScore.toFixed(1)` with the compiler
 * satisfied throughout.
 *
 * Normalising here rather than at each render site keeps the fix in one place
 * and keeps it true for every consumer of the model — the profile page, the
 * dashboard widgets and `isProfileComplete` all read these fields. It also
 * holds if the shape regresses again upstream: this response crosses the Go
 * Gateway, which re-serialises it.
 */
function toNumberOrNull(value: unknown): number | null {
  if (value === null || value === undefined || value === "") return null;
  const parsed = typeof value === "number" ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export function normalizeCurrentUser(raw: unknown): CurrentUser {
  const user = raw as CurrentUser & { profile?: unknown };
  const profile = user?.profile as UserProfileDetail | null | undefined;
  if (!profile) return { ...user, profile: null } as CurrentUser;

  return {
    ...user,
    profile: {
      ...profile,
      gpa: toNumberOrNull(profile.gpa),
      ieltsScore: toNumberOrNull(profile.ieltsScore),
      ects: toNumberOrNull(profile.ects),
      // Defaulted rather than nulled: the model declares these non-nullable and
      // the columns are NOT NULL with a 0 default, so 0 is the correct floor.
      workExperienceYears: toNumberOrNull(profile.workExperienceYears) ?? 0,
      extracurricularsScore: toNumberOrNull(profile.extracurricularsScore) ?? 0,
      targetCountries: Array.isArray(profile.targetCountries)
        ? profile.targetCountries
        : [],
    },
  };
}
