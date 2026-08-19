"use client";

import { useMemo, useState } from "react";
import { ArrowLeft, ArrowRight, Info } from "lucide-react";
import {
  Alert,
  Button,
  Combobox,
  Field,
  Heading,
  MultiCombobox,
  Select,
  Text,
} from "@/components/ui";
import {
  FIELDS_OF_STUDY,
  STUDY_DESTINATIONS,
  TARGET_DEGREE_LEVELS,
  flagEmoji,
  hasCatalogueCoverage,
  intakeOptions,
} from "@/lib/reference-data";
import type { TargetsData } from "./types";

interface TargetsStepProps {
  /** This is the wizard's last step: onComplete submits the whole draft. */
  onComplete: (data: TargetsData) => void;
  onBack: () => void;
  initialData: TargetsData;
  /** True while the wizard's PUT /api/profile call (triggered after this
   * step) is in flight, so the Finish button reflects that too. */
  finishing: boolean;
}

type Errors = Partial<Record<keyof TargetsData, string>>;

// More than a handful of target countries is not a preference, it is the
// absence of one -- and it widens RAG's candidate query for no benefit.
const MAX_DESTINATIONS = 5;

export default function TargetsStep({
  onComplete,
  onBack,
  initialData,
  finishing,
}: TargetsStepProps) {
  const [formData, setFormData] = useState<TargetsData>(initialData);
  const [errors, setErrors] = useState<Errors>({});

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

  const majorOptions = useMemo(
    () => FIELDS_OF_STUDY.map((f) => ({ value: f, label: f })),
    [],
  );

  const intakes = useMemo(() => intakeOptions(), []);

  // Warn rather than block: the catalogue is Europe-first today, and telling
  // someone their choice is invalid would be a lie about their ambitions.
  // Saying it will return fewer matches *now* is true and actionable.
  const uncoveredChoices = formData.destinations.filter(
    (name) => !hasCatalogueCoverage(name),
  );
  const noCoveredChoice =
    formData.destinations.length > 0 &&
    uncoveredChoices.length === formData.destinations.length;

  function validate(): Errors {
    const next: Errors = {};
    if (formData.destinations.length === 0) {
      next.destinations =
        "Pick at least one country — you can change this later from your profile.";
    }
    if (!formData.targetDegree) {
      next.targetDegree = "Select the degree level you're applying for.";
    }
    if (!formData.targetMajor.trim()) {
      next.targetMajor = "Enter the field you want to study — e.g. Data Science.";
    }
    if (!formData.targetIntake) {
      next.targetIntake = "Select roughly when you want to start.";
    }
    return next;
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const nextErrors = validate();
    setErrors(nextErrors);
    if (Object.keys(nextErrors).length === 0) onComplete(formData);
  }

  function set<K extends keyof TargetsData>(key: K, value: TargetsData[K]) {
    setFormData((prev) => ({ ...prev, [key]: value }));
    if (errors[key]) setErrors((prev) => ({ ...prev, [key]: undefined }));
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-6">
      <div>
        <Heading as="h2" size="md">
          Where do you want to study?
        </Heading>
        <Text size="sm" tone="muted" className="mt-1">
          These are starting points — Dalil will broaden the search as you chat.
        </Text>
      </div>

      <Field
        label="Destination countries"
        required
        hint={`Search and add up to ${MAX_DESTINATIONS}.`}
        error={errors.destinations}
      >
        {/* No explicit id: the surrounding Field owns the control id, and
            passing one here would leave its <label for> pointing at nothing —
            the field would have no accessible name at all. */}
        <MultiCombobox
          options={countryOptions}
          values={formData.destinations}
          onChange={(v) => set("destinations", v)}
          max={MAX_DESTINATIONS}
          placeholder="Search countries…"
          invalid={Boolean(errors.destinations)}
          emptyMessage="No country matches that search."
        />
      </Field>

      {uncoveredChoices.length > 0 && (
        <Alert tone={noCoveredChoice ? "warning" : "info"} announce="none" icon={Info}>
          {noCoveredChoice
            ? "Our programme catalogue is Europe-first at the moment, so these choices will return few or no matches yet. Adding Germany, the Netherlands, Sweden, Italy or Switzerland will give you results straight away — everything else still works."
            : `We have fewer programmes in ${uncoveredChoices.join(", ")} so far, so most of your matches will come from your other choices.`}
        </Alert>
      )}

      <Field label="Target degree" required error={errors.targetDegree}>
        <Select
          name="targetDegree"
          placeholder="Select your target degree"
          value={formData.targetDegree}
          onChange={(e) => set("targetDegree", e.target.value)}
        >
          {TARGET_DEGREE_LEVELS.map((level) => (
            <option key={level.value} value={level.value}>
              {level.label}
            </option>
          ))}
        </Select>
      </Field>

      <Field
        label="Intended major / research field"
        required
        error={errors.targetMajor}
        hint="Not listed? Type your own and press Enter."
      >
        <Combobox
          name="targetMajor"
          options={majorOptions}
          value={formData.targetMajor}
          onChange={(v) => set("targetMajor", v)}
          allowCustomValue
          placeholder="e.g. Data Science"
        />
      </Field>

      <Field label="Target intake term" required error={errors.targetIntake}>
        <Select
          name="targetIntake"
          placeholder="Select an intake term"
          value={formData.targetIntake}
          onChange={(e) => set("targetIntake", e.target.value)}
        >
          {intakes.map((intake) => (
            <option key={intake} value={intake}>
              {intake}
            </option>
          ))}
        </Select>
      </Field>

      <div className="flex flex-col-reverse gap-3 sm:flex-row">
        <Button
          type="button"
          variant="secondary"
          size="lg"
          leadingIcon={ArrowLeft}
          onClick={onBack}
          disabled={finishing}
        >
          Back
        </Button>
        <Button
          type="submit"
          size="lg"
          fullWidth
          trailingIcon={ArrowRight}
          loading={finishing}
          loadingLabel="Saving your profile"
        >
          Finish
        </Button>
      </div>
    </form>
  );
}
