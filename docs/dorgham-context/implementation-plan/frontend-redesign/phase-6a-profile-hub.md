# Phase 6a — Profile Hub High-Impact Uplift

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `/profile` lead with the outcomes of the user's data (programme matches, exam progress) instead of burying them under a long form, and make "how complete am I?" an honest, actionable answer derived from what the matcher actually reads.

**Architecture:** Five surgical changes to the existing page, no new backend. A new pure helper (`lib/profile-readiness.ts`) derives matching readiness from the fields `services/rag`'s gates and scoring genuinely consume. A new completeness card renders that readiness as a `Progress` meter with per-field "fix it" buttons that deep-link into the form. `app/(app)/profile/page.tsx` becomes a header plus three URL-synced tabs (Matches | Exam Progress | Edit profile). Because Radix unmounts inactive tab panels, opportunity-match fetching is lifted out of the panel into a `useOpportunityMatches` hook owned by the page, which also makes "re-rank after the profile changed" possible without burning the 20-searches-per-hour quota.

**Tech Stack:** Next.js 16 App Router (client components), React 19, react-hook-form, Radix Tabs via `@/components/ui`, Vitest + Testing Library, Playwright.

## Scope

Implements the five High-priority findings from the profile UI/UX review:

1. Promote outcomes above the edit form (tabs).
2. Add a completeness meter.
3. Make completeness honest about matching readiness.
4. Group the form into named sections.
5. Refresh matches after the profile changes.

This is an early, focused execution of the "Profile redesign" section of [phase-6-polish.md](phase-6-polish.md). It does **not** do the rest of Phase 6 (checklist timeline, coming-soon shells, app-wide motion/contrast/keyboard/Lighthouse sweep).

## Global Constraints

- **No backend changes.** Only already-deployed endpoints: `GET /api/profile`, `PUT /api/profile`, `POST /api/opportunities/query`.
- **`isProfileComplete()` in `services/frontend/app/types/profile.ts` must not change.** It drives the post-login redirect (`components/auth/LoginForm.tsx`), the sidebar nudge (`components/ui/sidebar.tsx`), the dashboard widgets, and `/opportunities` gating. Matching readiness is a **new, separate** signal.
- **Programme matching is rate-limited to 20 searches per hour per account** (Gateway `middleware.AIRateLimiter`, `"opportunity_search"`). No polling, no fetch-per-keystroke, no fetch-per-tab-flip.
- **Autosave-on-blur stays.** No Save button, no Edit/Cancel mode.
- **Design system only:** import primitives from `@/components/ui`. No raw hex, no `gray-*` classes (token-discipline scan).
- **Every form input keeps using `Field`** so `aria-describedby` / `aria-invalid` / `role="alert"` wiring stays automatic.
- All commands run from `services/frontend`.
- Commit style matches the repo: `feat(profile): …`, `refac(profile): …`, `test(profile): …`.

## Decisions Already Made

- **Tab state is synced to a URL query param** (`?tab=matches|progress|edit`), so a refresh or a shared link lands on the same tab. `matches` is the default and is omitted from the URL.
- **`matchReadiness()` is a new helper**, used by the completeness meter and by the matches surface as a soft signal. The hard "can we search at all" gate stays on `isProfileComplete()` — narrowing that gate would take matches *away* from users who see them today, which is a regression, not an improvement.

## File Structure

| File | Responsibility |
| --- | --- |
| `lib/profile-readiness.ts` (new) | Pure: which fields matching reads, and how far along this profile is. |
| `components/profile/form-section.tsx` (new) | Presentational: a titled, anchored group of form fields. |
| `components/profile/profile-completeness-card.tsx` (new) | Renders readiness as a meter plus per-missing-field jump buttons. |
| `components/profile/use-opportunity-matches.ts` (new) | Owns match fetching/state so it survives tab switches; decides when a re-rank is warranted. |
| `components/profile/use-profile-tab.ts` (new) | URL-synced tab state. |
| `components/profile/opportunity-matches-section.tsx` (modify) | Becomes presentational; state moves to the hook. |
| `components/profile/profile-form.tsx` (modify) | Fields grouped into sections; gains an `onSaved` passthrough. |
| `components/profile/use-profile-autosave.ts` (modify) | Gains an `onSaved` callback fired after a successful PUT. |
| `app/(app)/profile/page.tsx` (modify) | Composition: header, account + completeness, three tabs, focus handoff. |

Deliberately **not** done: extracting the IELTS block out of `profile-form.tsx`. It would need `control`, `register`, `setValue`, four watched values, `fieldError` and `saveFromBlur` threaded through props — more risk than the ~120 lines it saves. Wrapping it in a section is enough.

---

### Task 1: Matching-readiness helper

**Files:**
- Create: `services/frontend/lib/profile-readiness.ts`
- Test: `services/frontend/test/unit/profile-readiness.test.ts`

**Interfaces:**
- Consumes: `UserProfileDetail` from `@/app/types/profile`.
- Produces: `MATCH_FIELDS: readonly MatchField[]`, `matchReadiness(profile: UserProfileDetail | null): MatchReadiness`, and types `MatchField`, `MatchFieldKey`, `MatchReadiness`, `ProfileSectionId`. `MatchReadiness` is `{ filled: number; total: number; missing: MatchField[]; ready: boolean }`. `ProfileSectionId` is the union `"profile-section-academic" | "profile-section-ielts" | "profile-section-destinations"` — Task 2 puts those exact ids on DOM nodes and Task 3 links to them.

- [ ] **Step 1: Write the failing test**

Create `services/frontend/test/unit/profile-readiness.test.ts`:

```ts
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `npx vitest run test/unit/profile-readiness.test.ts`
Expected: FAIL — `Failed to resolve import "@/lib/profile-readiness"`.

- [ ] **Step 3: Write the implementation**

Create `services/frontend/lib/profile-readiness.ts`:

```ts
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
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `npx vitest run test/unit/profile-readiness.test.ts`
Expected: PASS, 8 tests.

- [ ] **Step 5: Commit**

```bash
git add services/frontend/lib/profile-readiness.ts services/frontend/test/unit/profile-readiness.test.ts
git commit -m "feat(profile): derive matching readiness from the matcher's own fields"
```

---

### Task 2: Group the application form into named sections

**Files:**
- Create: `services/frontend/components/profile/form-section.tsx`
- Modify: `services/frontend/components/profile/profile-form.tsx`
- Test: `services/frontend/test/unit/profile-form-sections.test.tsx`

**Interfaces:**
- Consumes: `ProfileSectionId` from Task 1.
- Produces: `FormSection` component; DOM anchors `#profile-section-academic`, `#profile-section-ielts`, `#profile-section-experience`, `#profile-section-destinations` inside the rendered form. Task 3 and Task 5 scroll to and focus these.

**Section mapping.** Existing field blocks move verbatim — no field is added, removed, relabelled, or rewired, and every `Controller`/`register`/`saveFromBlur` wiring travels with its block. Line numbers are the current `profile-form.tsx` as of this plan; confirm the block boundaries by eye before cutting.

| Section id | Heading | Blocks moved into it (`profile-form.tsx` lines) |
| --- | --- | --- |
| `profile-section-academic` | Academic background | Degree level (168–191); Field of study (193–215); GPA + Scale grid (241–278); ECTS credits (280–296) |
| `profile-section-ielts` | English (IELTS) | The `bg-canvas-subtle` IELTS block — four `BandScoreInput`s plus the overall-band card (298–417) |
| `profile-section-experience` | Experience | The Work experience + Extracurriculars grid (419–455) |
| `profile-section-destinations` | Study preferences | Intended Master's field (217–239); Target countries (457–478) |

Untouched and staying at the top of the `<form>`, above the first section: the `aria-live` save-status row (145–160) and the `saveError` `Alert` (162–166). The closing "Leaving a field blank…" `Text` (480–483) stays at the bottom, after the last section.

Moving "Field of study" (what you studied) into Academic background and "Intended Master's field" (what you want to study) into Study preferences is the point of the grouping: those two inputs were adjacent and near-identically named, and the section headings now do the disambiguating.

- [ ] **Step 1: Write the failing test**

Create `services/frontend/test/unit/profile-form-sections.test.tsx`:

```tsx
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { ProfileForm } from "@/components/profile/profile-form";
import type { UserProfileDetail } from "@/app/types/profile";

const PROFILE: UserProfileDetail = {
  userId: "user-1",
  degreeLevel: "Bachelors",
  gpa: 3.2,
  gpaScale: "4.0",
  ects: 180,
  ieltsScore: 7,
  ieltsListening: 7,
  ieltsReading: 7,
  ieltsWriting: 7,
  ieltsSpeaking: 7,
  targetCountries: ["Germany"],
  fieldOfStudy: "Computer Science",
  targetFieldOfStudy: "Software Engineering",
  workExperienceYears: 1,
  extracurricularsScore: 5,
};

describe("ProfileForm sections", () => {
  it("groups the fields under named section headings", () => {
    render(<ProfileForm profile={PROFILE} />);
    expect(
      screen.getByRole("heading", { name: "Academic background" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "English (IELTS)" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Experience" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Study preferences" }),
    ).toBeInTheDocument();
  });

  it("exposes the anchors the completeness card deep-links to", () => {
    const { container } = render(<ProfileForm profile={PROFILE} />);
    expect(container.querySelector("#profile-section-academic")).not.toBeNull();
    expect(container.querySelector("#profile-section-ielts")).not.toBeNull();
    expect(
      container.querySelector("#profile-section-destinations"),
    ).not.toBeNull();
  });

  it("keeps the field labels the existing tests select on", () => {
    render(<ProfileForm profile={PROFILE} />);
    expect(screen.getByLabelText("GPA")).toBeInTheDocument();
    expect(screen.getByLabelText("ECTS credits")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `npx vitest run test/unit/profile-form-sections.test.tsx`
Expected: FAIL — `Unable to find an accessible element with the role "heading" and name "Academic background"`.

- [ ] **Step 3: Create the section component**

Create `services/frontend/components/profile/form-section.tsx`:

```tsx
import type { ReactNode } from "react";
import { Heading, Text } from "@/components/ui";
import type { ProfileSectionId } from "@/lib/profile-readiness";

/**
 * A titled group of form fields with a stable anchor id.
 *
 * The id is what the completeness card scrolls to, so it is typed against the
 * same union the readiness helper hands out — a section that nothing can link
 * to, or a link to a section that does not exist, both fail to compile.
 */
export function FormSection({
  id,
  title,
  description,
  children,
}: {
  id: ProfileSectionId | "profile-section-experience";
  title: string;
  description?: string;
  children: ReactNode;
}) {
  return (
    <section
      id={id}
      aria-labelledby={`${id}-heading`}
      className="flex scroll-mt-24 flex-col gap-5 border-t border-border pt-6 first:border-t-0 first:pt-0"
    >
      <div>
        <Heading as="h3" size="xs" id={`${id}-heading`}>
          {title}
        </Heading>
        {description && (
          <Text size="sm" tone="muted" className="mt-1">
            {description}
          </Text>
        )}
      </div>
      {children}
    </section>
  );
}
```

- [ ] **Step 4: Wrap the existing fields in sections**

In `services/frontend/components/profile/profile-form.tsx`, add the import:

```tsx
import { FormSection } from "./form-section";
```

Then re-nest the existing JSX inside `<form>` into this shape. The autosave status row and the `saveError` `Alert` stay exactly where they are, above the first section. Every field block is **moved unchanged** — same `Controller`/`register` wiring, same `saveFromBlur()` calls, same labels, hints and error props:

```tsx
      <FormSection
        id="profile-section-academic"
        title="Academic background"
        description="What you have already studied. Matching gates on these."
      >
        {/* moved verbatim: the "Degree level" Field block */}
        {/* moved verbatim: the "Field of study" Field block */}
        {/* moved verbatim: the GPA + Scale grid div */}
        {/* moved verbatim: the "ECTS credits" Field block */}
      </FormSection>

      <FormSection
        id="profile-section-ielts"
        title="English (IELTS)"
        description="Your reported test scores, not practice results."
      >
        {/* moved verbatim: the existing rounded-card bg-canvas-subtle block
            containing the four BandScoreInputs and the overall-band card */}
      </FormSection>

      <FormSection id="profile-section-experience" title="Experience">
        {/* moved verbatim: the grid div holding "Work experience" and
            "Extracurriculars" */}
      </FormSection>

      <FormSection
        id="profile-section-destinations"
        title="Study preferences"
        description="What you want next. This is what programme matching ranks on."
      >
        {/* moved verbatim: the "Intended Master's field" Field block */}
        {/* moved verbatim: the "Target countries" Field block */}
      </FormSection>

      <Text size="sm" tone="subtle">
        Leaving a field blank keeps whatever is already saved — there is no way
        to clear a single value yet.
      </Text>
```

Two adjustments while re-nesting:

1. The outer `<form>` keeps `className="flex flex-col gap-5"`; change it to `className="flex flex-col gap-6"` so the section rules have room to read as separators.
2. The IELTS block's own intro sentence ("Enter the four section bands from your IELTS report…") is now duplicated by the section description. Delete the section description on `profile-section-ielts`'s `FormSection` **or** the block's intro `<Text>` — keep the block's intro, and set the `FormSection` description to `"Your reported test scores, not practice results."` as written above, which says something different.

- [ ] **Step 5: Run the test to verify it passes**

Run: `npx vitest run test/unit/profile-form-sections.test.tsx`
Expected: PASS, 3 tests.

- [ ] **Step 6: Run the full unit suite and typecheck**

Run: `npx vitest run && npx tsc --noEmit`
Expected: PASS, no type errors. `test/unit/profile-form.test.ts` must still pass untouched — it imports `payloadFromValues`/`validateProfile` from this file, and neither moved.

- [ ] **Step 7: Commit**

```bash
git add services/frontend/components/profile/form-section.tsx services/frontend/components/profile/profile-form.tsx services/frontend/test/unit/profile-form-sections.test.tsx
git commit -m "refac(profile): group application fields into named sections"
```

---

### Task 3: Completeness card

**Files:**
- Create: `services/frontend/components/profile/profile-completeness-card.tsx`
- Test: `services/frontend/test/unit/profile-completeness-card.test.tsx`

**Interfaces:**
- Consumes: `matchReadiness`, `MatchField`, `ProfileSectionId` (Task 1); the section anchors (Task 2).
- Produces: `<ProfileCompletenessCard profile={UserProfileDetail | null} onFix={(section: ProfileSectionId) => void} />`. Task 5 supplies `onFix`.

- [ ] **Step 1: Write the failing test**

Create `services/frontend/test/unit/profile-completeness-card.test.tsx`:

```tsx
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ProfileCompletenessCard } from "@/components/profile/profile-completeness-card";
import type { UserProfileDetail } from "@/app/types/profile";

const PARTIAL: UserProfileDetail = {
  userId: "user-1",
  degreeLevel: "Bachelors",
  gpa: 3.2,
  gpaScale: "4.0",
  ects: null,
  ieltsScore: null,
  ieltsListening: null,
  ieltsReading: null,
  ieltsWriting: null,
  ieltsSpeaking: null,
  targetCountries: [],
  fieldOfStudy: "Computer Science",
  targetFieldOfStudy: null,
  workExperienceYears: 0,
  extracurricularsScore: 0,
};

const READY: UserProfileDetail = {
  ...PARTIAL,
  ects: 180,
  ieltsScore: 7,
  targetCountries: ["Germany"],
};

describe("ProfileCompletenessCard", () => {
  it("reports how many matching details are present", () => {
    render(<ProfileCompletenessCard profile={PARTIAL} onFix={vi.fn()} />);
    const meter = screen.getByRole("progressbar");
    expect(meter).toHaveAttribute("aria-valuenow", "3");
    expect(meter).toHaveAttribute("aria-valuemax", "6");
    expect(screen.getByText("3 of 6 details")).toBeInTheDocument();
  });

  it("offers a jump button for each missing detail", async () => {
    const onFix = vi.fn();
    render(<ProfileCompletenessCard profile={PARTIAL} onFix={onFix} />);

    await userEvent.click(
      screen.getByRole("button", { name: "Add ECTS credits" }),
    );
    expect(onFix).toHaveBeenCalledWith("profile-section-academic");

    await userEvent.click(
      screen.getByRole("button", { name: "Add Target countries" }),
    );
    expect(onFix).toHaveBeenCalledWith("profile-section-destinations");
  });

  it("congratulates a complete profile instead of listing gaps", () => {
    render(<ProfileCompletenessCard profile={READY} onFix={vi.fn()} />);
    expect(screen.getByRole("progressbar")).toHaveAttribute(
      "aria-valuenow",
      "6",
    );
    expect(screen.queryByRole("button", { name: /^Add / })).toBeNull();
    expect(
      screen.getByText(/everything programme matching reads/i),
    ).toBeInTheDocument();
  });

  it("links to the guided wizard while details are missing", () => {
    render(<ProfileCompletenessCard profile={PARTIAL} onFix={vi.fn()} />);
    expect(
      screen.getByRole("link", { name: "Use the guided wizard" }),
    ).toHaveAttribute("href", "/onboarding");
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `npx vitest run test/unit/profile-completeness-card.test.tsx`
Expected: FAIL — `Failed to resolve import "@/components/profile/profile-completeness-card"`.

- [ ] **Step 3: Write the implementation**

Create `services/frontend/components/profile/profile-completeness-card.tsx`:

```tsx
"use client";

import Link from "next/link";
import { Button, Card, Progress, Text } from "@/components/ui";
import {
  matchReadiness,
  type ProfileSectionId,
} from "@/lib/profile-readiness";
import type { UserProfileDetail } from "@/app/types/profile";

/**
 * Matching readiness as a meter plus one button per gap.
 *
 * Replaces the page's binary "Incomplete" badge, which told a user that
 * something was missing without saying what, and sat next to an Alert saying
 * the same thing again.
 */
export function ProfileCompletenessCard({
  profile,
  onFix,
}: {
  profile: UserProfileDetail | null;
  onFix: (section: ProfileSectionId) => void;
}) {
  const { filled, total, missing, ready } = matchReadiness(profile);

  return (
    <Card>
      <Progress
        value={filled}
        max={total}
        label="Matching readiness"
        valueText={`${filled} of ${total} details`}
        showValue
        tone={ready ? "success" : "brand"}
      />

      <Text size="sm" tone="muted" className="mt-3">
        {ready
          ? "Your profile has everything programme matching reads."
          : "Programme matching ranks on these details. The more you add, the better the shortlist."}
      </Text>

      {missing.length > 0 && (
        <>
          <ul className="mt-3 flex flex-wrap gap-2">
            {missing.map((field) => (
              <li key={field.key}>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => onFix(field.section)}
                >
                  Add {field.label}
                </Button>
              </li>
            ))}
          </ul>
          <Text size="sm" tone="subtle" className="mt-3">
            Prefer to be walked through it?{" "}
            <Link
              href="/onboarding"
              className="font-medium text-brand-fg underline underline-offset-2"
            >
              Use the guided wizard
            </Link>
          </Text>
        </>
      )}
    </Card>
  );
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `npx vitest run test/unit/profile-completeness-card.test.tsx`
Expected: PASS, 4 tests.

- [ ] **Step 5: Commit**

```bash
git add services/frontend/components/profile/profile-completeness-card.tsx services/frontend/test/unit/profile-completeness-card.test.tsx
git commit -m "feat(profile): add a matching-readiness meter with per-gap jump buttons"
```

---

### Task 4: Lift opportunity-match fetching into a hook

This is a behaviour-preserving refactor, done **before** the tabs land. Radix unmounts an inactive tab panel, so leaving the fetch inside `OpportunityMatchesSection` would mean a fresh `POST /api/opportunities/query` every time the user returned to the Matches tab — against a 20-per-hour quota. Owning the state above the panel fixes that and is what makes Task 6's re-rank possible.

**Files:**
- Create: `services/frontend/components/profile/use-opportunity-matches.ts`
- Modify: `services/frontend/components/profile/opportunity-matches-section.tsx`
- Modify: `services/frontend/app/(app)/profile/page.tsx`
- Test: `services/frontend/test/unit/opportunity-matches-hook.test.tsx`

**Interfaces:**
- Produces: `useOpportunityMatches({ enabled: boolean; visible: boolean; savedAt: number }): { programs: MatchedProgram[]; status: MatchesStatus; error: string | null; retryAfter: string | null; reload: () => void }`, where `MatchesStatus = "loading" | "success" | "error" | "profile-incomplete" | "syncing" | "rate-limited"`.
- Produces: `OpportunityMatchesSection` now takes `{ programs, status, error, retryAfter, onReload, onFocusProfile? }` and holds no fetch state. Task 5 passes `visible`; until then the page passes `visible: true` and `savedAt: 0`, so behaviour is identical to today.

- [ ] **Step 1: Write the failing test**

Create `services/frontend/test/unit/opportunity-matches-hook.test.tsx`:

```tsx
import { afterEach, describe, expect, it, vi } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";

const apiMock = vi.hoisted(() => ({ searchOpportunities: vi.fn() }));
vi.mock("@/lib/opportunities-api", async (importOriginal) => {
  const actual =
    await importOriginal<typeof import("@/lib/opportunities-api")>();
  return { ...actual, searchOpportunities: apiMock.searchOpportunities };
});

const { useOpportunityMatches } = await import(
  "@/components/profile/use-opportunity-matches"
);

const PROGRAM = {
  programId: "prog-1",
  programName: "MSc Computer Science",
  university: "TU Munich",
  country: "Germany",
  deadline: null,
  result: { score: 85, blocked_by: null },
};

afterEach(() => {
  vi.clearAllMocks();
});

describe("useOpportunityMatches", () => {
  it("searches once when it is enabled and visible", async () => {
    apiMock.searchOpportunities.mockResolvedValue([PROGRAM]);

    const { result } = renderHook(() =>
      useOpportunityMatches({ enabled: true, visible: true, savedAt: 0 }),
    );

    await waitFor(() => expect(result.current.status).toBe("success"));
    expect(result.current.programs).toHaveLength(1);
    expect(apiMock.searchOpportunities).toHaveBeenCalledTimes(1);
  });

  it("does not search while the matches surface is hidden", async () => {
    apiMock.searchOpportunities.mockResolvedValue([]);

    renderHook(() =>
      useOpportunityMatches({ enabled: true, visible: false, savedAt: 0 }),
    );

    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(apiMock.searchOpportunities).not.toHaveBeenCalled();
  });

  it("does not search again when visibility toggles without a save", async () => {
    apiMock.searchOpportunities.mockResolvedValue([PROGRAM]);

    const { result, rerender } = renderHook(
      ({ visible }) =>
        useOpportunityMatches({ enabled: true, visible, savedAt: 0 }),
      { initialProps: { visible: true } },
    );
    await waitFor(() => expect(result.current.status).toBe("success"));

    rerender({ visible: false });
    rerender({ visible: true });

    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(apiMock.searchOpportunities).toHaveBeenCalledTimes(1);
  });

  it("re-ranks once when the profile was saved and the surface is shown again", async () => {
    apiMock.searchOpportunities.mockResolvedValue([PROGRAM]);

    const { result, rerender } = renderHook(
      ({ visible, savedAt }) =>
        useOpportunityMatches({ enabled: true, visible, savedAt }),
      { initialProps: { visible: true, savedAt: 0 } },
    );
    await waitFor(() => expect(result.current.status).toBe("success"));

    // Editing happens on another tab: two saves, no search.
    rerender({ visible: false, savedAt: 1 });
    rerender({ visible: false, savedAt: 2 });
    expect(apiMock.searchOpportunities).toHaveBeenCalledTimes(1);

    rerender({ visible: true, savedAt: 2 });
    await waitFor(() =>
      expect(apiMock.searchOpportunities).toHaveBeenCalledTimes(2),
    );
  });

  it("reports an incomplete profile without spending a search", async () => {
    const { result } = renderHook(() =>
      useOpportunityMatches({ enabled: false, visible: true, savedAt: 0 }),
    );

    await waitFor(() =>
      expect(result.current.status).toBe("profile-incomplete"),
    );
    expect(apiMock.searchOpportunities).not.toHaveBeenCalled();
  });

  it("surfaces the wait when the hourly search limit is hit", async () => {
    const { RateLimitedError } = await import("@/lib/opportunities-api");
    apiMock.searchOpportunities.mockRejectedValue(new RateLimitedError(120));

    const { result } = renderHook(() =>
      useOpportunityMatches({ enabled: true, visible: true, savedAt: 0 }),
    );

    await waitFor(() => expect(result.current.status).toBe("rate-limited"));
    expect(result.current.retryAfter).toBe("2 minutes");
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `npx vitest run test/unit/opportunity-matches-hook.test.tsx`
Expected: FAIL — `Failed to resolve import "@/components/profile/use-opportunity-matches"`.

- [ ] **Step 3: Write the hook**

Create `services/frontend/components/profile/use-opportunity-matches.ts`:

```ts
"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  ProfileNotReadyError,
  RateLimitedError,
  formatRetryAfter,
  searchOpportunities,
  type MatchedProgram,
} from "@/lib/opportunities-api";
import { useUpgradePrompt } from "@/components/subscription/upgrade-dialog";

export type MatchesStatus =
  | "loading"
  | "success"
  | "error"
  | "profile-incomplete"
  | "syncing"
  | "rate-limited";

const TOP_N = 10;

/**
 * Owns opportunity-match fetching for the profile hub.
 *
 * State lives here rather than in the matches panel because Radix unmounts an
 * inactive tab panel: a panel that fetched on mount would spend one of the
 * account's 20 hourly searches every time the user flicked back to the tab.
 *
 * A search happens only when the surface is visible AND the results on hand
 * are older than the last successful profile save (`savedAt`). Editing on
 * another tab therefore costs nothing until the user comes back to look.
 */
export function useOpportunityMatches({
  enabled,
  visible,
  savedAt,
}: {
  enabled: boolean;
  visible: boolean;
  savedAt: number;
}) {
  const upgrade = useUpgradePrompt();

  const [programs, setPrograms] = useState<MatchedProgram[]>([]);
  const [status, setStatus] = useState<MatchesStatus>(
    enabled ? "loading" : "profile-incomplete",
  );
  const [error, setError] = useState<string | null>(null);
  const [retryAfter, setRetryAfter] = useState<string | null>(null);

  const inFlight = useRef(false);
  /** The `savedAt` the held results were ranked against; -1 means never. */
  const loadedFor = useRef(-1);

  const load = useCallback(
    async (forSave: number) => {
      // Also what makes React's development double-effect issue one request.
      if (inFlight.current) return;
      inFlight.current = true;
      setStatus("loading");
      setError(null);

      try {
        const results = await searchOpportunities();
        setPrograms(results.slice(0, TOP_N));
        setStatus("success");
      } catch (err) {
        if (err instanceof ProfileNotReadyError) {
          setStatus("syncing");
        } else if (err instanceof RateLimitedError) {
          setRetryAfter(formatRetryAfter(err.retryAfterSeconds));
          setStatus("rate-limited");
        } else if (upgrade.handle(err)) {
          setError(null);
          setStatus("error");
        } else {
          setError(
            "We couldn't reach programme matching just now. Your profile is unchanged — try again in a moment.",
          );
          setStatus("error");
        }
      } finally {
        inFlight.current = false;
        // Recorded on failure too: a failed search must not turn every tab
        // switch into an automatic retry. `reload` is the way back.
        loadedFor.current = forSave;
      }
    },
    [upgrade],
  );

  const reload = useCallback(() => {
    void load(savedAt);
  }, [load, savedAt]);

  useEffect(() => {
    if (!enabled) {
      setPrograms([]);
      setStatus("profile-incomplete");
      loadedFor.current = -1;
      return;
    }
    if (!visible) return;
    if (loadedFor.current === savedAt) return;
    void load(savedAt);
  }, [enabled, visible, savedAt, load]);

  return { programs, status, error, retryAfter, reload };
}
```

- [ ] **Step 4: Make the section presentational**

In `services/frontend/components/profile/opportunity-matches-section.tsx`:

1. Delete the `useState`/`useEffect`/`useCallback`/`useRef` imports and the whole `load` function, the `Status` type, the `TOP_N` constant, the `useUpgradePrompt` call, and every `useState` except `selected` (the detail modal is genuinely local to this component).
2. Delete the imports of `ProfileNotReadyError`, `RateLimitedError`, `formatRetryAfter`, `searchOpportunities` — they now live in the hook. Keep `type MatchedProgram`.
3. Import the status type: `import type { MatchesStatus } from "./use-opportunity-matches";`
4. Change the signature to:

```tsx
export function OpportunityMatchesSection({
  programs,
  status,
  error,
  retryAfter,
  onReload,
  onFocusProfile,
}: {
  programs: MatchedProgram[];
  status: MatchesStatus;
  error: string | null;
  retryAfter: string | null;
  onReload: () => void;
  onFocusProfile?: () => void;
}) {
  const [selected, setSelected] = useState<MatchedProgram | null>(null);
```

5. Replace every `onClick={() => void load()}` with `onClick={onReload}`. The JSX for all six status branches is otherwise unchanged.

- [ ] **Step 5: Point the page at the hook**

In `services/frontend/app/(app)/profile/page.tsx`, add:

```tsx
import { useOpportunityMatches } from "@/components/profile/use-opportunity-matches";
```

Inside `ProfilePage`, below `useCurrentUser()`:

```tsx
  const profileComplete = isProfileComplete(user?.profile ?? null);
  const matches = useOpportunityMatches({
    enabled: profileComplete,
    visible: true,
    savedAt: 0,
  });
```

and replace the existing usage with:

```tsx
                <OpportunityMatchesSection
                  programs={matches.programs}
                  status={matches.status}
                  error={matches.error}
                  retryAfter={matches.retryAfter}
                  onReload={matches.reload}
                  onFocusProfile={focusApplicationProfile}
                />
```

Hooks must run unconditionally, so `useOpportunityMatches` is called at the top of the component even though the tabs only render once `status === "success"` — that is why `enabled` is derived with `user?.profile ?? null` rather than inside the success branch.

- [ ] **Step 6: Run the tests**

Run: `npx vitest run test/unit/opportunity-matches-hook.test.tsx && npx tsc --noEmit`
Expected: PASS, 6 tests, no type errors.

- [ ] **Step 7: Verify the matches e2e is unchanged**

Run: `npx playwright test test/e2e/profile.spec.ts`
Expected: all 3 tests PASS with no edits to the spec — this task changes no behaviour.

- [ ] **Step 8: Commit**

```bash
git add services/frontend/components/profile/use-opportunity-matches.ts services/frontend/components/profile/opportunity-matches-section.tsx "services/frontend/app/(app)/profile/page.tsx" services/frontend/test/unit/opportunity-matches-hook.test.tsx
git commit -m "refac(profile): own match fetching above the panel that renders it"
```

---

### Task 5: URL-synced tabs and the new page composition

**Files:**
- Create: `services/frontend/components/profile/use-profile-tab.ts`
- Modify: `services/frontend/app/(app)/profile/page.tsx`
- Modify: `services/frontend/test/e2e/profile.spec.ts`
- Test: `services/frontend/test/unit/profile-tab.test.tsx`

**Interfaces:**
- Produces: `PROFILE_TABS`, `type ProfileTab = "matches" | "progress" | "edit"`, `useProfileTab(): { tab: ProfileTab; setTab: (next: ProfileTab) => void }`.
- Consumes: `ProfileCompletenessCard` (Task 3), section anchors (Task 2), `useOpportunityMatches` (Task 4).

- [ ] **Step 1: Write the failing test for the tab hook**

Create `services/frontend/test/unit/profile-tab.test.tsx`:

```tsx
import { afterEach, describe, expect, it, vi } from "vitest";
import { renderHook, act } from "@testing-library/react";

const nav = vi.hoisted(() => ({
  params: new URLSearchParams(),
  replace: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: nav.replace }),
  usePathname: () => "/profile",
  useSearchParams: () => nav.params,
}));

const { useProfileTab } = await import("@/components/profile/use-profile-tab");

afterEach(() => {
  nav.params = new URLSearchParams();
  vi.clearAllMocks();
});

describe("useProfileTab", () => {
  it("defaults to matches when the URL says nothing", () => {
    const { result } = renderHook(() => useProfileTab());
    expect(result.current.tab).toBe("matches");
  });

  it("reads the tab out of the query string", () => {
    nav.params = new URLSearchParams("tab=edit");
    const { result } = renderHook(() => useProfileTab());
    expect(result.current.tab).toBe("edit");
  });

  it("falls back to matches for a tab name it does not know", () => {
    nav.params = new URLSearchParams("tab=nonsense");
    const { result } = renderHook(() => useProfileTab());
    expect(result.current.tab).toBe("matches");
  });

  it("writes the tab to the URL without adding history entries", () => {
    const { result } = renderHook(() => useProfileTab());
    act(() => result.current.setTab("progress"));
    expect(nav.replace).toHaveBeenCalledWith("/profile?tab=progress", {
      scroll: false,
    });
  });

  it("drops the param again when returning to the default tab", () => {
    nav.params = new URLSearchParams("tab=edit");
    const { result } = renderHook(() => useProfileTab());
    act(() => result.current.setTab("matches"));
    expect(nav.replace).toHaveBeenCalledWith("/profile", { scroll: false });
  });

  it("keeps unrelated query params intact", () => {
    nav.params = new URLSearchParams("ref=email");
    const { result } = renderHook(() => useProfileTab());
    act(() => result.current.setTab("edit"));
    expect(nav.replace).toHaveBeenCalledWith("/profile?ref=email&tab=edit", {
      scroll: false,
    });
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `npx vitest run test/unit/profile-tab.test.tsx`
Expected: FAIL — `Failed to resolve import "@/components/profile/use-profile-tab"`.

- [ ] **Step 3: Write the tab hook**

Create `services/frontend/components/profile/use-profile-tab.ts`:

```ts
"use client";

import { useCallback } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

export const PROFILE_TABS = ["matches", "progress", "edit"] as const;
export type ProfileTab = (typeof PROFILE_TABS)[number];

const DEFAULT_TAB: ProfileTab = "matches";

function parseTab(value: string | null): ProfileTab {
  return PROFILE_TABS.includes(value as ProfileTab)
    ? (value as ProfileTab)
    : DEFAULT_TAB;
}

/**
 * Which profile tab is open, kept in `?tab=`.
 *
 * In the URL so a refresh, a bookmark or a shared link lands where the user
 * was. `router.replace`, not `push`: flicking between tabs is not navigation,
 * and filling the back stack with it would strand the user on their own page.
 */
export function useProfileTab() {
  const params = useSearchParams();
  const pathname = usePathname();
  const router = useRouter();

  const tab = parseTab(params.get("tab"));

  const setTab = useCallback(
    (next: ProfileTab) => {
      const search = new URLSearchParams(params.toString());
      if (next === DEFAULT_TAB) search.delete("tab");
      else search.set("tab", next);
      const query = search.toString();
      router.replace(query ? `${pathname}?${query}` : pathname, {
        scroll: false,
      });
    },
    [params, pathname, router],
  );

  return { tab, setTab };
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `npx vitest run test/unit/profile-tab.test.tsx`
Expected: PASS, 6 tests.

- [ ] **Step 5: Rewrite the page**

Replace the whole of `services/frontend/app/(app)/profile/page.tsx` with:

```tsx
"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Sparkles } from "lucide-react";
import { useCurrentUser } from "@/app/hooks/useCurrentUser";
import { isProfileComplete } from "@/app/types/profile";
import { DEFAULT_UPGRADE_URL } from "@/lib/subscription";
import type { ProfileSectionId } from "@/lib/profile-readiness";
import { ProfileForm } from "@/components/profile/profile-form";
import { ProfileCompletenessCard } from "@/components/profile/profile-completeness-card";
import { OpportunityMatchesSection } from "@/components/profile/opportunity-matches-section";
import { useOpportunityMatches } from "@/components/profile/use-opportunity-matches";
import {
  useProfileTab,
  type ProfileTab,
} from "@/components/profile/use-profile-tab";
import { CvUploadPanel } from "@/components/cv/cv-upload-panel";
import {
  Alert,
  Badge,
  Button,
  Card,
  Heading,
  Icon,
  PageContainer,
  Skeleton,
  Tabs,
  TabsList,
  TabsPanel,
  TabsTrigger,
  Text,
} from "@/components/ui";
import { ExamProgressTab } from "@/components/profile/exam-progress";

/**
 * Profile hub — header → account + matching readiness → Matches | Exam
 * Progress | Edit profile (GOA-029 + GOA-062).
 *
 * The edit form used to sit between the user and the two surfaces that show
 * what the form is *for*. It is now a tab of equal standing, with the meter in
 * the header carrying the "you still owe us X" message the form's inline
 * badge used to.
 */
export default function ProfilePage() {
  // useProfileTab reads useSearchParams, which opts this subtree out of static
  // prerendering and so needs a boundary — same reason exam/results has one.
  return (
    <Suspense fallback={<ProfileSkeleton />}>
      <ProfileHub />
    </Suspense>
  );
}

function ProfileSkeleton() {
  return (
    <PageContainer size="md">
      <div className="space-y-4" aria-busy="true" aria-label="Loading profile">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-28 w-full rounded-card" />
        <Skeleton className="h-28 w-full rounded-card" />
        <Skeleton className="h-64 w-full rounded-card" />
      </div>
    </PageContainer>
  );
}

function ProfileHub() {
  const { user, status, error, retry, patchProfile } = useCurrentUser();
  const { tab, setTab } = useProfileTab();

  const [pendingSection, setPendingSection] =
    useState<ProfileSectionId | null>(null);

  const matches = useOpportunityMatches({
    enabled: isProfileComplete(user?.profile ?? null),
    visible: tab === "matches",
    savedAt: 0,
  });

  /** Open the form on the section that owns a missing field, and focus it. */
  const focusSection = useCallback(
    (section: ProfileSectionId) => {
      setTab("edit");
      setPendingSection(section);
    },
    [setTab],
  );

  // Runs after the edit panel has been committed to the DOM, so the anchor the
  // user asked for exists by the time we look for it.
  useEffect(() => {
    if (tab !== "edit" || !pendingSection) return;
    const node = document.getElementById(pendingSection);
    if (!node) return;
    node.scrollIntoView({ behavior: "smooth", block: "start" });
    node
      .querySelector<HTMLElement>(
        "input:not([type='hidden']), select, textarea, button, [tabindex]:not([tabindex='-1'])",
      )
      ?.focus({ preventScroll: true });
    setPendingSection(null);
  }, [tab, pendingSection]);

  return (
    <PageContainer size="md">
      <div className="mb-6">
        <Badge tone="brand" pill>
          Your Profile
        </Badge>
        <Heading as="h1" size="xl" className="mt-2">
          Account &amp; Application Profile
        </Heading>
        <Text size="sm" tone="muted" className="mt-1">
          Everything here feeds programme matching. Keep it current and your
          matches stay current — changes save when you leave a field.
        </Text>
      </div>

      {status === "loading" && (
        <div
          className="space-y-2"
          aria-busy="true"
          aria-label="Loading profile"
        >
          <Skeleton />
          <Skeleton />
          <Skeleton />
        </div>
      )}

      {status === "error" && (
        <Alert
          tone="danger"
          announce="assertive"
          actions={
            <>
              <Button variant="danger" size="sm" onClick={retry}>
                Retry
              </Button>
              <Button variant="link" size="sm" asChild>
                <Link href="/login">Log in again</Link>
              </Button>
            </>
          }
        >
          {error}
        </Alert>
      )}

      {status === "success" && user && (
        <div className="space-y-6">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Card>
              <Heading as="h2" size="xs" className="mb-4 text-fg-muted">
                Account
              </Heading>
              <dl className="grid grid-cols-1 gap-4 text-sm">
                <ReadOnlyField label="Email" value={user.email} />
                <ReadOnlyField
                  label="Subscription"
                  value={
                    user.subscriptionTier === "paid" ? "Dalil Pro" : "Free plan"
                  }
                />
              </dl>
              <div className="mt-4 flex flex-wrap items-center gap-3 border-t border-border pt-4">
                <Icon icon={Sparkles} size="sm" className="text-brand-fg" />
                <Text size="sm" tone="muted" className="flex-1">
                  {user.subscriptionTier === "paid"
                    ? "Review your plan or cancel any time."
                    : "IELTS exams, essay scoring and CV review are part of Dalil Pro."}
                </Text>
                <Button size="sm" variant="outline" asChild>
                  <Link
                    href={
                      user.subscriptionTier === "paid"
                        ? "/billing/manage"
                        : DEFAULT_UPGRADE_URL
                    }
                  >
                    {user.subscriptionTier === "paid"
                      ? "Manage subscription"
                      : "See plans"}
                  </Link>
                </Button>
              </div>
            </Card>

            <ProfileCompletenessCard
              profile={user.profile}
              onFix={focusSection}
            />
          </div>

          <Tabs
            value={tab}
            onValueChange={(value) => setTab(value as ProfileTab)}
          >
            <TabsList variant="underline">
              <TabsTrigger value="matches">Matches</TabsTrigger>
              <TabsTrigger value="progress">Exam Progress</TabsTrigger>
              <TabsTrigger value="edit">Edit profile</TabsTrigger>
            </TabsList>

            <TabsPanel value="matches">
              <OpportunityMatchesSection
                programs={matches.programs}
                status={matches.status}
                error={matches.error}
                retryAfter={matches.retryAfter}
                onReload={matches.reload}
                onFocusProfile={() => focusSection("profile-section-academic")}
              />
            </TabsPanel>

            <TabsPanel value="progress">
              <ExamProgressTab />
            </TabsPanel>

            <TabsPanel value="edit" className="space-y-6">
              <Card>
                <Heading as="h2" size="xs" className="mb-4 text-fg-muted">
                  Application Profile
                </Heading>
                <ProfileForm
                  profile={user.profile}
                  onOptimisticUser={patchProfile}
                  onSaveError={() => {
                    // Hard autosave failure: resync from server (rolls the
                    // form back to what is actually stored).
                    void retry();
                  }}
                />
              </Card>

              <Card>
                <Heading as="h2" size="xs" id="profile-cv-heading">
                  CV
                </Heading>
                <Text size="sm" tone="muted" className="mt-1 mb-4">
                  Upload or replace your CV here. AI review stays on the CV
                  Review page.
                </Text>
                <CvUploadPanel showReviewLink />
              </Card>
            </TabsPanel>
          </Tabs>
        </div>
      )}
    </PageContainer>
  );
}

function ReadOnlyField({
  label,
  value,
}: {
  label: string;
  value: string | number | null;
}) {
  return (
    <div>
      <dt className="text-xs text-fg-subtle">{label}</dt>
      <dd className="mt-0.5 text-fg">
        {value === null || value === undefined || value === "" ? "—" : value}
      </dd>
    </div>
  );
}
```

What this deliberately removes, and why: the in-form `Incomplete` badge and the "Your application profile is incomplete…" `Alert` both said, less precisely, what the completeness card now says once — including its own link to the guided wizard. The `id="application-profile"` wrapper and `focusApplicationProfile` are gone because focus now targets a specific section anchor instead of the top of the whole form.

- [ ] **Step 6: Update the profile e2e spec**

Two of the three tests in `services/frontend/test/e2e/profile.spec.ts` reach for form controls that now live behind the Edit tab. Change their navigation only:

In `"profile autosaves GPA on blur and persists after refresh"`:

```ts
  await page.goto("/profile?tab=edit");
```

In `"CV upload on profile shows Processing then ready filename"`:

```ts
  await page.goto("/profile?tab=edit");
```

`"opportunity matches show score bar and open detail modal"` keeps `await page.goto("/profile")` — Matches is the default tab. `page.reload()` in the GPA test keeps the query string, so the assertion after reload still finds the GPA field.

Add one test covering the new deep link, after the existing tests:

```ts
test("a missing detail jumps to the section that owns it", async ({ page }) => {
  await mockProfileGet(page, {
    ...BASE_PROFILE,
    profile: { ...BASE_PROFILE.profile, ects: null },
  });
  await page.route(`${CV_API_BASE}/latest`, (route) =>
    route.fulfill(withCors({ detail: "No CV uploaded yet" }, 404)),
  );
  await page.route(`${GATEWAY}/api/opportunities/query`, (route) =>
    route.fulfill(withCors({ programs: [] })),
  );

  await page.goto("/profile");
  await page.getByRole("button", { name: "Add ECTS credits" }).click();

  await expect(page.getByRole("tab", { name: "Edit profile" })).toHaveAttribute(
    "aria-selected",
    "true",
  );
  await expect(page.getByLabel("ECTS credits")).toBeVisible();
  await expect(page).toHaveURL(/\?tab=edit/);
});
```

- [ ] **Step 7: Run everything**

Run: `npx vitest run && npx tsc --noEmit && npm run build`
Expected: all unit tests PASS, no type errors, build succeeds (a missing Suspense boundary around `useSearchParams` fails `next build`, so a green build is the real check on Step 5's boundary).

Run: `npx playwright test test/e2e/profile.spec.ts test/e2e/exam-progress.spec.ts`
Expected: PASS. `exam-progress.spec.ts` clicks `getByRole("tab", { name: "Exam Progress" })`, whose accessible name is unchanged, so it needs no edit.

- [ ] **Step 8: Commit**

```bash
git add "services/frontend/app/(app)/profile/page.tsx" services/frontend/components/profile/use-profile-tab.ts services/frontend/test/unit/profile-tab.test.tsx services/frontend/test/e2e/profile.spec.ts
git commit -m "feat(profile): lead with matches and progress behind URL-synced tabs"
```

---

### Task 6: Re-rank matches after the profile changes

**Files:**
- Modify: `services/frontend/components/profile/use-profile-autosave.ts`
- Modify: `services/frontend/components/profile/profile-form.tsx`
- Modify: `services/frontend/app/(app)/profile/page.tsx`
- Test: `services/frontend/test/unit/profile-autosave-saved.test.tsx`

**Interfaces:**
- Consumes: `useOpportunityMatches`'s `savedAt` (Task 4), which already re-ranks when `savedAt` changes and the surface becomes visible.
- Produces: `useProfileAutosave({ …, onSaved?: () => void })` and `<ProfileForm onSaved={() => void} />`.

- [ ] **Step 1: Write the failing test**

Create `services/frontend/test/unit/profile-autosave-saved.test.tsx`:

```tsx
import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

const apiMock = vi.hoisted(() => ({
  authApi: { updateProfile: vi.fn() },
  apiErrorMessage: () => "Could not save your profile.",
}));
vi.mock("@/lib/api", () => apiMock);

const { ProfileForm } = await import("@/components/profile/profile-form");

import type { UserProfileDetail } from "@/app/types/profile";

const PROFILE: UserProfileDetail = {
  userId: "user-1",
  degreeLevel: "Bachelors",
  gpa: 3.2,
  gpaScale: "4.0",
  ects: 180,
  ieltsScore: 7,
  ieltsListening: 7,
  ieltsReading: 7,
  ieltsWriting: 7,
  ieltsSpeaking: 7,
  targetCountries: ["Germany"],
  fieldOfStudy: "Computer Science",
  targetFieldOfStudy: "Software Engineering",
  workExperienceYears: 1,
  extracurricularsScore: 5,
};

afterEach(() => {
  vi.clearAllMocks();
});

describe("ProfileForm onSaved", () => {
  it("announces a successful save so matches can be re-ranked", async () => {
    apiMock.authApi.updateProfile.mockResolvedValue({});
    const onSaved = vi.fn();

    render(<ProfileForm profile={PROFILE} onSaved={onSaved} />);

    const gpa = screen.getByLabelText("GPA");
    await userEvent.clear(gpa);
    await userEvent.type(gpa, "3.9");
    await userEvent.tab();

    await waitFor(() => expect(onSaved).toHaveBeenCalledTimes(1));
  });

  it("stays quiet when the save fails", async () => {
    apiMock.authApi.updateProfile.mockRejectedValue(new Error("boom"));
    const onSaved = vi.fn();

    render(<ProfileForm profile={PROFILE} onSaved={onSaved} />);

    const gpa = screen.getByLabelText("GPA");
    await userEvent.clear(gpa);
    await userEvent.type(gpa, "3.7");
    await userEvent.tab();

    await waitFor(() =>
      expect(apiMock.authApi.updateProfile).toHaveBeenCalled(),
    );
    expect(onSaved).not.toHaveBeenCalled();
  });

  it("stays quiet when nothing actually changed", async () => {
    apiMock.authApi.updateProfile.mockResolvedValue({});
    const onSaved = vi.fn();

    render(<ProfileForm profile={PROFILE} onSaved={onSaved} />);

    await userEvent.click(screen.getByLabelText("GPA"));
    await userEvent.tab();

    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(apiMock.authApi.updateProfile).not.toHaveBeenCalled();
    expect(onSaved).not.toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `npx vitest run test/unit/profile-autosave-saved.test.tsx`
Expected: FAIL — the first test times out because `onSaved` is never called (the prop does not exist yet).

- [ ] **Step 3: Fire the callback from the autosave hook**

In `services/frontend/components/profile/use-profile-autosave.ts`, add `onSaved` to the parameter object:

```ts
export function useProfileAutosave({
  getValues,
  onOptimisticUser,
  onSaveError,
  onSaved,
}: {
  getValues: () => ProfileFormValues;
  onOptimisticUser?: (partial: Partial<UserProfileDetail>) => void;
  onSaveError?: (message: string) => void;
  /** Fired after a PUT that actually changed something succeeded. */
  onSaved?: () => void;
}) {
```

and call it in the success branch:

```ts
    try {
      await authApi.updateProfile(payload);
      lastSaved.current = fingerprint;
      setSaveState("saved");
      onSaved?.();
    } catch (err) {
```

Add `onSaved` to the `saveFromBlur` dependency array:

```ts
  }, [getValues, onOptimisticUser, onSaveError, onSaved]);
```

The existing no-op guards already give the last two tests: a validation failure returns before the PUT, and an unchanged fingerprint returns before it too.

- [ ] **Step 4: Pass it through the form**

In `services/frontend/components/profile/profile-form.tsx`:

```tsx
export function ProfileForm({
  profile,
  onOptimisticUser,
  onSaveError,
  onSaved,
}: {
  profile: UserProfileDetail | null;
  onOptimisticUser?: (partial: Partial<UserProfileDetail>) => void;
  onSaveError?: (message: string) => void;
  onSaved?: () => void;
}) {
```

and forward it:

```tsx
    useProfileAutosave({
      getValues,
      onOptimisticUser,
      onSaveError,
      onSaved,
    });
```

- [ ] **Step 5: Wire the page**

In `services/frontend/app/(app)/profile/page.tsx`, add the counter beside `pendingSection`:

```tsx
  // Bumped on every successful save. useOpportunityMatches re-ranks the next
  // time the Matches tab is shown — not on the save itself, because matching
  // is capped at 20 searches an hour and a form is many saves.
  const [savedAt, setSavedAt] = useState(0);
```

feed it to the hook:

```tsx
  const matches = useOpportunityMatches({
    enabled: isProfileComplete(user?.profile ?? null),
    visible: tab === "matches",
    savedAt,
  });
```

and raise it from the form:

```tsx
                <ProfileForm
                  profile={user.profile}
                  onOptimisticUser={patchProfile}
                  onSaved={() => setSavedAt((n) => n + 1)}
                  onSaveError={() => {
                    void retry();
                  }}
                />
```

- [ ] **Step 6: Run the tests**

Run: `npx vitest run test/unit/profile-autosave-saved.test.tsx && npx vitest run && npx tsc --noEmit`
Expected: PASS, 3 new tests plus the whole suite, no type errors.

- [ ] **Step 7: Add the end-to-end proof**

Append to `services/frontend/test/e2e/profile.spec.ts`:

```ts
test("editing the profile re-ranks matches when you return to them", async ({
  page,
}) => {
  let searches = 0;

  await page.route(`${GATEWAY}/api/profile`, async (route) => {
    if (route.request().method() === "PUT") {
      await route.fulfill(withCors({ ok: true }));
      return;
    }
    await route.fulfill(withCors(BASE_PROFILE));
  });
  await page.route(`${CV_API_BASE}/latest`, (route) =>
    route.fulfill(withCors({ detail: "No CV uploaded yet" }, 404)),
  );
  await page.route(`${GATEWAY}/api/opportunities/query`, (route) => {
    searches += 1;
    return route.fulfill(withCors({ programs: [] }));
  });

  await page.goto("/profile");
  await expect(page.getByText("No programmes matched yet")).toBeVisible();
  expect(searches).toBe(1);

  await page.getByRole("tab", { name: "Edit profile" }).click();
  const gpa = page.getByLabel("GPA");
  await gpa.fill("3.9");
  await gpa.blur();
  await expect(page.getByText("Saved")).toBeVisible();

  // Flicking to a third tab must not spend a search.
  await page.getByRole("tab", { name: "Exam Progress" }).click();
  expect(searches).toBe(1);

  await page.getByRole("tab", { name: "Matches" }).click();
  await expect.poll(() => searches).toBe(2);
});
```

Run: `npx playwright test test/e2e/profile.spec.ts`
Expected: all 5 tests PASS.

- [ ] **Step 8: Commit**

```bash
git add services/frontend/components/profile/use-profile-autosave.ts services/frontend/components/profile/profile-form.tsx "services/frontend/app/(app)/profile/page.tsx" services/frontend/test/unit/profile-autosave-saved.test.tsx services/frontend/test/e2e/profile.spec.ts
git commit -m "feat(profile): re-rank matches after a profile edit, once per visit"
```

---

## Verification Strategy

Run from `services/frontend` after the last task:

1. `npx tsc --noEmit` — clean.
2. `npx vitest run` — clean, including the pre-existing `profile-form.test.ts`, `profile-normalize.test.ts`, `dashboard-widgets.test.tsx`, `app-shell.test.tsx`.
3. `npm run build` — clean. This is the real check that the `useSearchParams` Suspense boundary is correct.
4. `npx playwright test test/e2e/profile.spec.ts test/e2e/exam-progress.spec.ts test/e2e/dashboard.spec.ts` — clean. The dashboard suite is included because `ProgressWidget` renders its own, separate completeness meter and must be unaffected.
5. Manual pass at 320, 375, 768, 1024 and 1440px on `/profile`, `/profile?tab=progress`, `/profile?tab=edit`: the three-trigger tab row scrolls rather than widening the page, and the account/completeness grid collapses to one column below `sm`.
6. Manual keyboard pass: Tab to the tab row, move between tabs with Left/Right arrows, Tab into the panel. From the Matches tab, press Enter on an "Add …" button and confirm focus lands inside the named form section rather than at the top of the page or nowhere.
7. Manual quota check with devtools open: load `/profile`, flick between all three tabs five times, confirm exactly one `POST /api/opportunities/query`. Edit one field, return to Matches, confirm exactly one more.

## Out of Scope (reviewed and deferred)

These came out of the same review and are deliberately not in this plan: the avatar treatment in the header; disambiguating "estimated overall band" (practice) from the reported IELTS overall; the `Dalil Pro` / `GOA Pro` copy inconsistency between the account card and the exam-progress upgrade state; skill-specific deep links from Weak Areas into `/exam`; the nested pill tabs inside the band-trend chart. None of them blocks the five high-impact changes above.
