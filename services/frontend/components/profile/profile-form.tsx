"use client";

import { useMemo, useState } from "react";
import { Save, X } from "lucide-react";
import { authApi, apiErrorMessage, type UpdateProfilePayload } from "@/lib/api";
import { isValidBand, parseBand } from "@/lib/ielts";
import {
  DEGREE_LEVELS,
  FIELDS_OF_STUDY,
  STUDY_DESTINATIONS,
  flagEmoji,
  hasCatalogueCoverage,
} from "@/lib/reference-data";
import type { UserProfileDetail } from "@/app/types/profile";
import {
  Alert,
  Button,
  Combobox,
  Field,
  Input,
  MultiCombobox,
  Select,
  Text,
} from "@/components/ui";

/* ------------------------------------------------------------------ *
 * The editable half of the profile page.
 *
 * PUT /api/profile already existed and was called from exactly one place --
 * the last step of the onboarding wizard. So every field the wizard collects
 * was write-once: the profile page rendered them into a <dl> and offered no
 * way to change any of them, and the only route back to the wizard was the
 * sidebar's "Complete Profile" nudge, which disappears the moment one field
 * is filled in. A user whose IELTS result improved, or who decided to look at
 * a different country, had no way to say so.
 *
 * Field constraints below mirror UpdateProfileDto exactly
 * (services/user/src/profile/dto/update-profile.dto.ts) so a rejection is
 * caught here rather than surfacing as a class-validator message array.
 * ------------------------------------------------------------------ */

export interface ProfileFormValues {
  degreeLevel: string;
  fieldOfStudy: string;
  gpa: string;
  gpaScale: "4.0" | "100";
  ects: string;
  ieltsScore: string;
  workExperienceYears: string;
  extracurricularsScore: string;
  targetCountries: string[];
}

type Errors = Partial<Record<keyof ProfileFormValues, string>>;

export function valuesFromProfile(
  profile: UserProfileDetail | null,
): ProfileFormValues {
  return {
    degreeLevel: profile?.degreeLevel ?? "",
    fieldOfStudy: profile?.fieldOfStudy ?? "",
    gpa: profile?.gpa != null ? String(profile.gpa) : "",
    gpaScale: profile?.gpaScale ?? "4.0",
    ects: profile?.ects != null ? String(profile.ects) : "",
    ieltsScore: profile?.ieltsScore != null ? String(profile.ieltsScore) : "",
    workExperienceYears:
      profile?.workExperienceYears != null
        ? String(profile.workExperienceYears)
        : "",
    extracurricularsScore:
      profile?.extracurricularsScore != null
        ? String(profile.extracurricularsScore)
        : "",
    targetCountries: profile?.targetCountries ?? [],
  };
}

export function validateProfile(values: ProfileFormValues): Errors {
  const errors: Errors = {};

  if (values.gpa.trim()) {
    const gpa = Number(values.gpa);
    const max = values.gpaScale === "4.0" ? 4 : 100;
    if (Number.isNaN(gpa)) errors.gpa = "Enter a number, e.g. 3.4.";
    else if (gpa < 0 || gpa > max) {
      errors.gpa = `On the ${values.gpaScale} scale, that should be between 0 and ${max}.`;
    }
  }

  if (values.ects.trim()) {
    const ects = Number(values.ects);
    if (Number.isNaN(ects) || ects < 0) {
      errors.ects = "Enter a whole number of credits, e.g. 180.";
    } else if (ects > 600) {
      errors.ects = "That looks too high — ECTS totals are usually under 400.";
    }
  }

  if (values.ieltsScore.trim()) {
    const band = Number(values.ieltsScore);
    if (Number.isNaN(band)) errors.ieltsScore = "Enter a band between 0 and 9.";
    else if (band < 0 || band > 9) errors.ieltsScore = "Bands run from 0 to 9.";
    else if (!isValidBand(band)) {
      errors.ieltsScore = "Bands go in half steps — 6.5, not 6.4.";
    }
  }

  if (values.workExperienceYears.trim()) {
    const years = Number(values.workExperienceYears);
    if (!Number.isInteger(years) || years < 0) {
      errors.workExperienceYears = "Enter a whole number of years, e.g. 2.";
    } else if (years > 60) {
      errors.workExperienceYears = "That looks too high — enter years, not months.";
    }
  }

  if (values.extracurricularsScore.trim()) {
    const score = Number(values.extracurricularsScore);
    if (!Number.isInteger(score) || score < 0 || score > 10) {
      errors.extracurricularsScore = "Rate your activities from 0 to 10.";
    }
  }

  return errors;
}

/**
 * Builds the PUT body.
 *
 * Every field is optional in UpdateProfileDto, so an emptied box is sent as an
 * omission rather than as null — the backend has no "clear this field"
 * semantics, and inventing one client-side by sending 0 would be worse than
 * leaving the old value in place.
 */
export function payloadFromValues(
  values: ProfileFormValues,
): UpdateProfilePayload {
  const payload: UpdateProfilePayload = {};

  if (values.degreeLevel) payload.degreeLevel = values.degreeLevel;
  if (values.fieldOfStudy.trim()) payload.fieldOfStudy = values.fieldOfStudy.trim();

  if (values.gpa.trim()) {
    payload.gpa = Number(values.gpa);
    payload.gpaScale = values.gpaScale;
  }
  if (values.ects.trim()) payload.ects = Number(values.ects);

  const band = parseBand(values.ieltsScore);
  if (band !== null) payload.ieltsScore = band;

  if (values.workExperienceYears.trim()) {
    payload.workExperienceYears = Number(values.workExperienceYears);
  }
  if (values.extracurricularsScore.trim()) {
    payload.extracurricularsScore = Number(values.extracurricularsScore);
  }

  payload.targetCountries = values.targetCountries;

  return payload;
}

export function ProfileForm({
  profile,
  onCancel,
  onSaved,
}: {
  profile: UserProfileDetail | null;
  onCancel: () => void;
  onSaved: () => void | Promise<void>;
}) {
  const [values, setValues] = useState<ProfileFormValues>(() =>
    valuesFromProfile(profile),
  );
  const [errors, setErrors] = useState<Errors>({});
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const countryOptions = useMemo(
    () =>
      STUDY_DESTINATIONS.map((country) => ({
        value: country.name,
        label: country.name,
        prefix: flagEmoji(country.code),
        description: hasCatalogueCoverage(country.name)
          ? "Programmes available now"
          : undefined,
      })),
    [],
  );

  const fieldOptions = useMemo(
    () => FIELDS_OF_STUDY.map((f) => ({ value: f, label: f })),
    [],
  );

  function set<K extends keyof ProfileFormValues>(
    key: K,
    value: ProfileFormValues[K],
  ) {
    setValues((prev) => ({ ...prev, [key]: value }));
    if (errors[key]) setErrors((prev) => ({ ...prev, [key]: undefined }));
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setSaveError(null);

    const nextErrors = validateProfile(values);
    setErrors(nextErrors);
    if (Object.keys(nextErrors).length > 0) return;

    setSaving(true);
    try {
      await authApi.updateProfile(payloadFromValues(values));
      await onSaved();
    } catch (err) {
      setSaveError(
        apiErrorMessage(err) ??
          "Could not save your profile. Your changes are still here — please try again.",
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-5">
      {saveError && (
        <Alert tone="danger" announce="assertive">
          {saveError}
        </Alert>
      )}

      <Field label="Degree level" error={errors.degreeLevel}>
        <Select
          name="degreeLevel"
          placeholder="Select your degree"
          value={values.degreeLevel}
          onChange={(e) => set("degreeLevel", e.target.value)}
        >
          {DEGREE_LEVELS.map((level) => (
            <option key={level.value} value={level.value}>
              {level.label}
            </option>
          ))}
        </Select>
      </Field>

      <Field
        label="Field of study"
        error={errors.fieldOfStudy}
        hint="Not listed? Type your own and press Enter."
      >
        <Combobox
          name="fieldOfStudy"
          options={fieldOptions}
          value={values.fieldOfStudy}
          onChange={(v) => set("fieldOfStudy", v)}
          allowCustomValue
          placeholder="e.g. Computer Science"
        />
      </Field>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-[1fr_auto] sm:items-start">
        <Field label="GPA" error={errors.gpa}>
          <Input
            type="number"
            name="gpa"
            inputMode="decimal"
            step="0.01"
            min={0}
            max={values.gpaScale === "4.0" ? 4 : 100}
            placeholder={values.gpaScale === "4.0" ? "e.g. 3.8" : "e.g. 85"}
            value={values.gpa}
            onChange={(e) => set("gpa", e.target.value)}
          />
        </Field>

        <Field label="Scale">
          <Select
            value={values.gpaScale}
            onChange={(e) => {
              set("gpaScale", e.target.value as "4.0" | "100");
              setErrors((prev) => ({ ...prev, gpa: undefined }));
            }}
            className="sm:w-28"
          >
            <option value="4.0">/ 4.0</option>
            <option value="100">/ 100</option>
          </Select>
        </Field>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Field
          label="ECTS credits"
          error={errors.ects}
          hint="A Bachelor's is typically 180–240."
        >
          <Input
            type="number"
            name="ects"
            inputMode="numeric"
            min={0}
            placeholder="e.g. 180"
            value={values.ects}
            onChange={(e) => set("ects", e.target.value)}
          />
        </Field>

        <Field
          label="IELTS overall band"
          error={errors.ieltsScore}
          hint="Half steps only — 6.0, 6.5, 7.0."
        >
          <Input
            type="number"
            name="ieltsScore"
            inputMode="decimal"
            step={0.5}
            min={0}
            max={9}
            placeholder="e.g. 7.0"
            value={values.ieltsScore}
            onChange={(e) => set("ieltsScore", e.target.value)}
          />
        </Field>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Field label="Work experience" error={errors.workExperienceYears}>
          <Input
            type="number"
            name="workExperienceYears"
            inputMode="numeric"
            min={0}
            placeholder="Years, e.g. 2"
            value={values.workExperienceYears}
            onChange={(e) => set("workExperienceYears", e.target.value)}
          />
        </Field>

        <Field
          label="Extracurriculars"
          error={errors.extracurricularsScore}
          hint="Self-rated 0–10: volunteering, research, leadership."
        >
          <Input
            type="number"
            name="extracurricularsScore"
            inputMode="numeric"
            min={0}
            max={10}
            placeholder="e.g. 6"
            value={values.extracurricularsScore}
            onChange={(e) => set("extracurricularsScore", e.target.value)}
          />
        </Field>
      </div>

      <Field
        label="Target countries"
        error={errors.targetCountries}
        hint="Where you'd like to study. This is what programme matching filters on."
      >
        {/* See TargetStep: the Field supplies the control id. */}
        <MultiCombobox
          options={countryOptions}
          values={values.targetCountries}
          onChange={(v) => set("targetCountries", v)}
          max={5}
          placeholder="Search countries…"
        />
      </Field>

      <Text size="sm" tone="subtle">
        Leaving a field blank keeps whatever is already saved — there is no way
        to clear a single value yet.
      </Text>

      <div className="flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
        <Button
          type="button"
          variant="secondary"
          leadingIcon={X}
          onClick={onCancel}
          disabled={saving}
        >
          Cancel
        </Button>
        <Button
          type="submit"
          leadingIcon={Save}
          loading={saving}
          loadingLabel="Saving your profile"
        >
          Save changes
        </Button>
      </div>
    </form>
  );
}
