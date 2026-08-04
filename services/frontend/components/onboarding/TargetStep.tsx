"use client";

import { useState } from "react";
import { ArrowLeft, ArrowRight } from "lucide-react";
import { cn } from "@/lib/cn";
import { Button, Field, Heading, Input, Select, Text } from "@/components/ui";
import { DESTINATION_COUNTRIES, type TargetsData } from "./types";

interface TargetsStepProps {
  onNext: (data: TargetsData) => void;
  onBack: () => void;
  initialData: TargetsData;
}

type Errors = Partial<Record<keyof TargetsData, string>>;

export default function TargetsStep({ onNext, onBack, initialData }: TargetsStepProps) {
  const [formData, setFormData] = useState<TargetsData>(initialData);
  const [errors, setErrors] = useState<Errors>({});

  function validate(): Errors {
    const next: Errors = {};
    if (formData.destinations.length === 0)
      next.destinations = "Select at least one destination country.";
    if (!formData.targetDegree) next.targetDegree = "Select your target degree level.";
    if (!formData.targetMajor.trim()) next.targetMajor = "Enter your intended field of study.";
    if (!formData.targetIntake) next.targetIntake = "Select your preferred start term.";
    return next;
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const nextErrors = validate();
    setErrors(nextErrors);
    if (Object.keys(nextErrors).length === 0) onNext(formData);
  }

  function toggleCountry(countryId: string) {
    setFormData((prev) => {
      const exists = prev.destinations.includes(countryId);
      return {
        ...prev,
        destinations: exists
          ? prev.destinations.filter((d) => d !== countryId)
          : [...prev.destinations, countryId],
      };
    });
    if (errors.destinations) setErrors((prev) => ({ ...prev, destinations: undefined }));
  }

  function set<K extends keyof TargetsData>(key: K, value: TargetsData[K]) {
    setFormData((prev) => ({ ...prev, [key]: value }));
    if (errors[key]) setErrors((prev) => ({ ...prev, [key]: undefined }));
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-6">
      <div>
        <Heading as="h2" size="md">
          Where do you want to study?
        </Heading>
        <Text size="sm" tone="muted" className="mt-1">
          These are starting points — GOA will broaden the search as you
          chat.
        </Text>
      </div>

      <Field label="Destination countries" hint="Select all that apply." error={errors.destinations}>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3" role="group">
          {DESTINATION_COUNTRIES.map((country) => {
            const selected = formData.destinations.includes(country.id);
            return (
              <label
                key={country.id}
                className={cn(
                  "cursor-pointer rounded-control border p-3 text-center text-sm font-medium transition-colors duration-120 ease-out",
                  selected
                    ? "border-brand bg-brand-subtle text-fg ring-1 ring-brand"
                    : "border-border text-fg-muted hover:border-border-strong hover:bg-canvas-subtle",
                )}
              >
                <input
                  type="checkbox"
                  checked={selected}
                  onChange={() => toggleCountry(country.id)}
                  className="sr-only"
                />
                {country.name}
              </label>
            );
          })}
        </div>
      </Field>

      <Field label="Target degree" required error={errors.targetDegree}>
        <Select
          name="targetDegree"
          placeholder="Select your target degree"
          value={formData.targetDegree}
          onChange={(e) => set("targetDegree", e.target.value)}
        >
          <option value="Bachelors">Bachelor&apos;s degree</option>
          <option value="Masters">Master&apos;s degree</option>
          <option value="PhD">Ph.D. / Doctorate</option>
        </Select>
      </Field>

      <Field label="Intended major / research field" required error={errors.targetMajor}>
        <Input
          name="targetMajor"
          placeholder="e.g. Data Science, Mechanical Engineering"
          value={formData.targetMajor}
          onChange={(e) => set("targetMajor", e.target.value)}
        />
      </Field>

      <Field label="Target intake term" required error={errors.targetIntake}>
        <Select
          name="targetIntake"
          placeholder="Select an intake term"
          value={formData.targetIntake}
          onChange={(e) => set("targetIntake", e.target.value)}
        >
          <option value="Fall 2026">Fall 2026</option>
          <option value="Spring 2027">Spring 2027</option>
          <option value="Fall 2027">Fall 2027</option>
          <option value="Later">Later</option>
        </Select>
      </Field>

      <div className="flex gap-3">
        <Button type="button" variant="secondary" size="lg" leadingIcon={ArrowLeft} onClick={onBack}>
          Back
        </Button>
        <Button type="submit" size="lg" fullWidth trailingIcon={ArrowRight}>
          Continue
        </Button>
      </div>
    </form>
  );
}
