"use client";

import { useEffect, useMemo } from "react";
import { Controller, useForm } from "react-hook-form";
import { Pencil, RotateCcw } from "lucide-react";
import { FormSection } from "./form-section";
import {
  bandDescriptor,
  computeOverallBand,
  formatBand,
  parseBand,
} from "@/lib/ielts";
import {
  DEGREE_LEVELS,
  FIELDS_OF_STUDY,
  STUDY_DESTINATIONS,
  flagEmoji,
  hasCatalogueCoverage,
} from "@/lib/reference-data";
import type { UserProfileDetail } from "@/app/types/profile";
import { BandScoreInput } from "@/components/onboarding/ielts-score-input";
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
import {
  valuesFromProfile,
  type ProfileFormValues,
} from "./profile-form-model";
import { useProfileAutosave } from "./use-profile-autosave";

export type { ProfileFormValues } from "./profile-form-model";
export {
  payloadFromValues,
  parsedDetailFromValues,
  validateProfile,
  valuesFromProfile,
} from "./profile-form-model";

const IELTS_SECTIONS = [
  { name: "ieltsListening" as const, label: "Listening" },
  { name: "ieltsReading" as const, label: "Reading" },
  { name: "ieltsWriting" as const, label: "Writing" },
  { name: "ieltsSpeaking" as const, label: "Speaking" },
];

export function ProfileForm({
  profile,
  onOptimisticUser,
  onSaveError,
}: {
  profile: UserProfileDetail | null;
  onOptimisticUser?: (partial: Partial<UserProfileDetail>) => void;
  onSaveError?: (message: string) => void;
}) {
  const defaults = useMemo(() => valuesFromProfile(profile), [profile]);

  const { control, register, getValues, setValue, watch } =
    useForm<ProfileFormValues>({
      defaultValues: defaults,
      mode: "onBlur",
    });

  const { saveState, saveError, fieldErrors, saveFromBlur, seedLastSaved } =
    useProfileAutosave({
      getValues,
      onOptimisticUser,
      onSaveError,
    });

  // Seed the fingerprint once on mount. Optimistic parent patches must not
  // reset the form (that would fight in-progress edits). A failed save calls
  // retry() which unmounts this form while status=loading, then remounts with
  // server values — that is the rollback path.
  useEffect(() => {
    seedLastSaved(defaults);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- mount only
  }, []);

  const listening = watch("ieltsListening");
  const reading = watch("ieltsReading");
  const writing = watch("ieltsWriting");
  const speaking = watch("ieltsSpeaking");
  const overrideOverall = watch("overrideOverall");
  const ieltsScore = watch("ieltsScore");
  const gpaScale = watch("gpaScale");

  const computedOverall = useMemo(
    () =>
      computeOverallBand({
        listening: parseBand(listening),
        reading: parseBand(reading),
        writing: parseBand(writing),
        speaking: parseBand(speaking),
      }),
    [listening, reading, writing, speaking],
  );

  useEffect(() => {
    if (overrideOverall) return;
    const next = computedOverall === null ? "" : formatBand(computedOverall);
    if (next !== getValues("ieltsScore")) {
      setValue("ieltsScore", next, { shouldDirty: false });
    }
  }, [computedOverall, overrideOverall, getValues, setValue]);

  const overallValue = parseBand(ieltsScore);
  const overrideDiffers =
    overrideOverall &&
    overallValue !== null &&
    computedOverall !== null &&
    overallValue !== computedOverall;

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

  const fieldError = (name: keyof ProfileFormValues) => fieldErrors[name];

  return (
    <form
      noValidate
      className="flex flex-col gap-6"
      onSubmit={(e) => e.preventDefault()}
    >
      <div className="flex items-center justify-between gap-3">
        <div aria-live="polite" className="sr-only">
          {saveState === "saving" ? "Saving profile" : null}
          {saveState === "saved" ? "Profile saved" : null}
          {saveState === "error" && saveError ? saveError : null}
        </div>
        <Text size="sm" tone="subtle" aria-live="polite">
          {saveState === "saving"
            ? "Saving…"
            : saveState === "saved"
              ? "Saved"
              : saveState === "error"
                ? "Couldn’t save"
                : "Changes save when you leave a field"}
        </Text>
      </div>

      {saveError && (
        <Alert tone="danger" announce="assertive">
          {saveError}
        </Alert>
      )}

      <FormSection
        id="profile-section-academic"
        title="Academic background"
        description="What you have already studied. Matching gates on these."
      >
        <Field label="Degree level" error={fieldError("degreeLevel")}>
          <Controller
            name="degreeLevel"
            control={control}
            render={({ field }) => (
              <Select
                name={field.name}
                placeholder="Select your degree"
                value={field.value}
                onChange={(e) => {
                  field.onChange(e.target.value);
                  void saveFromBlur();
                }}
                onBlur={field.onBlur}
              >
                {DEGREE_LEVELS.map((level) => (
                  <option key={level.value} value={level.value}>
                    {level.label}
                  </option>
                ))}
              </Select>
            )}
          />
        </Field>

        <Field
          label="Field of study"
          error={fieldError("fieldOfStudy")}
          hint="Not listed? Type your own and press Enter."
        >
          <Controller
            name="fieldOfStudy"
            control={control}
            render={({ field }) => (
              <Combobox
                name={field.name}
                options={fieldOptions}
                value={field.value}
                onChange={(v) => {
                  field.onChange(v);
                  void saveFromBlur();
                }}
                allowCustomValue
                placeholder="e.g. Computer Science"
              />
            )}
          />
        </Field>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-[1fr_auto] sm:items-start">
          <Field label="GPA" error={fieldError("gpa")}>
            <Input
              type="number"
              inputMode="decimal"
              step="0.01"
              min={0}
              max={gpaScale === "4.0" ? 4 : 100}
              placeholder={gpaScale === "4.0" ? "e.g. 3.8" : "e.g. 85"}
              {...register("gpa", {
                onBlur: () => {
                  void saveFromBlur();
                },
              })}
            />
          </Field>

          <Field label="Scale">
            <Controller
              name="gpaScale"
              control={control}
              render={({ field }) => (
                <Select
                  value={field.value}
                  onChange={(e) => {
                    field.onChange(e.target.value as "4.0" | "100");
                    void saveFromBlur();
                  }}
                  onBlur={field.onBlur}
                  className="sm:w-28"
                >
                  <option value="4.0">/ 4.0</option>
                  <option value="100">/ 100</option>
                </Select>
              )}
            />
          </Field>
        </div>

        <Field
          label="ECTS credits"
          error={fieldError("ects")}
          hint="A Bachelor's is typically 180–240."
        >
          <Input
            type="number"
            inputMode="numeric"
            min={0}
            placeholder="e.g. 180"
            {...register("ects", {
              onBlur: () => {
                void saveFromBlur();
              },
            })}
          />
        </Field>
      </FormSection>

      <FormSection
        id="profile-section-ielts"
        title="English (IELTS)"
        description="Your reported test scores, not practice results."
      >
        <div className="flex flex-col gap-5 rounded-card border border-border bg-canvas-subtle p-4 sm:p-5">
        <Text size="sm" tone="muted">
          Enter the four section bands from your IELTS report. Overall is
          calculated for you unless you edit it.
        </Text>

        <div className="flex flex-col gap-5">
          {IELTS_SECTIONS.map((section) => (
            <Controller
              key={section.name}
              name={section.name}
              control={control}
              render={({ field }) => (
                <BandScoreInput
                  id={section.name}
                  label={section.label}
                  value={field.value}
                  onChange={(v) => {
                    field.onChange(v);
                    void saveFromBlur();
                  }}
                  error={fieldError(section.name)}
                  compact
                />
              )}
            />
          ))}
        </div>

        <div className="rounded-card border border-brand-border bg-brand-subtle p-4">
          <div className="flex items-center justify-between gap-3">
            <div className="min-w-0">
              <Text size="sm" className="font-semibold text-brand-fg">
                Overall band
              </Text>
              <Text size="sm" tone="muted" className="mt-0.5">
                {overrideOverall
                  ? "Entered manually"
                  : computedOverall === null
                    ? "Fill in all four sections above"
                    : "Calculated from your four sections"}
              </Text>
            </div>

            {overrideOverall ? (
              <Input
                type="number"
                step={0.5}
                min={0}
                max={9}
                inputMode="decimal"
                aria-label="Overall band score"
                className="w-24 text-center text-base font-bold"
                {...register("ieltsScore", {
                  onBlur: () => {
                    void saveFromBlur();
                  },
                })}
              />
            ) : (
              <span
                aria-live="polite"
                className="shrink-0 text-3xl font-bold tabular-nums text-brand-fg"
              >
                {overallValue === null ? "—" : formatBand(overallValue)}
              </span>
            )}
          </div>

          {overallValue !== null && !overrideOverall && (
            <Text size="sm" tone="muted" className="mt-2">
              {bandDescriptor(overallValue)}
            </Text>
          )}

          {fieldError("ieltsScore") && (
            <p role="alert" className="mt-2 text-sm text-danger-fg">
              {fieldError("ieltsScore")}
            </p>
          )}

          {overrideDiffers && computedOverall !== null && (
            <Alert tone="warning" announce="none" className="mt-3">
              Your sections average to {formatBand(computedOverall)}. If your
              report says {formatBand(overallValue!)}, keep it — otherwise
              double-check the four bands above.
            </Alert>
          )}

          <div className="mt-3">
            {overrideOverall ? (
              <Button
                type="button"
                variant="link"
                size="sm"
                leadingIcon={RotateCcw}
                onClick={() => {
                  setValue("overrideOverall", false);
                  if (computedOverall !== null) {
                    setValue("ieltsScore", formatBand(computedOverall));
                  }
                  void saveFromBlur();
                }}
              >
                Calculate it for me
              </Button>
            ) : (
              <Button
                type="button"
                variant="link"
                size="sm"
                leadingIcon={Pencil}
                onClick={() => setValue("overrideOverall", true)}
              >
                Edit overall
              </Button>
            )}
          </div>
        </div>
        </div>
      </FormSection>

      <FormSection id="profile-section-experience" title="Experience">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field
            label="Work experience"
            error={fieldError("workExperienceYears")}
          >
            <Input
              type="number"
              inputMode="numeric"
              min={0}
              placeholder="Years, e.g. 2"
              {...register("workExperienceYears", {
                onBlur: () => {
                  void saveFromBlur();
                },
              })}
            />
          </Field>

          <Field
            label="Extracurriculars"
            error={fieldError("extracurricularsScore")}
            hint="Self-rated 0–10: volunteering, research, leadership."
          >
            <Input
              type="number"
              inputMode="numeric"
              min={0}
              max={10}
              placeholder="e.g. 6"
              {...register("extracurricularsScore", {
                onBlur: () => {
                  void saveFromBlur();
                },
              })}
            />
          </Field>
        </div>
      </FormSection>

      <FormSection
        id="profile-section-destinations"
        title="Study preferences"
        description="What you want next. This is what programme matching ranks on."
      >
        <Field
          label="Intended Master's field"
          error={fieldError("targetFieldOfStudy")}
          hint="This is the subject programme matching prioritises."
        >
          <Controller
            name="targetFieldOfStudy"
            control={control}
            render={({ field }) => (
              <Combobox
                name={field.name}
                options={fieldOptions}
                value={field.value}
                onChange={(v) => {
                  field.onChange(v);
                  void saveFromBlur();
                }}
                allowCustomValue
                placeholder="e.g. Software Engineering"
              />
            )}
          />
        </Field>

        <Field
          label="Target countries"
          error={fieldError("targetCountries")}
          hint="Where you'd like to study. This is what programme matching filters on."
        >
          <Controller
            name="targetCountries"
            control={control}
            render={({ field }) => (
              <MultiCombobox
                options={countryOptions}
                values={field.value}
                onChange={(v) => {
                  field.onChange(v);
                  void saveFromBlur();
                }}
                max={5}
                placeholder="Search countries…"
              />
            )}
          />
        </Field>
      </FormSection>

      <Text size="sm" tone="subtle">
        Leaving a field blank keeps whatever is already saved — there is no way
        to clear a single value yet.
      </Text>
    </form>
  );
}
