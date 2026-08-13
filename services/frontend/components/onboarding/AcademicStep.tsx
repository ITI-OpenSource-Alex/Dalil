"use client";

import { useMemo, useRef, useState } from "react";
import { ArrowRight } from "lucide-react";
import {
  Button,
  Combobox,
  Field,
  Heading,
  Input,
  Select,
  Text,
} from "@/components/ui";
import { DEGREE_LEVELS, FIELDS_OF_STUDY, UNIVERSITIES } from "@/lib/reference-data";
import type { AcademicData } from "./types";

interface AcademicStepProps {
  onNext: (data: AcademicData) => void;
  initialData: AcademicData;
}

type Errors = Partial<Record<keyof AcademicData, string>>;

const CURRENT_YEAR = new Date().getFullYear();
// Wide enough for a mature applicant's first degree at one end and an
// in-progress one at the other, narrow enough that a typo'd 2062 is caught.
const MIN_GRAD_YEAR = 1960;
const MAX_GRAD_YEAR = CURRENT_YEAR + 8;

export default function AcademicStep({ onNext, initialData }: AcademicStepProps) {
  const [formData, setFormData] = useState<AcademicData>(initialData);
  const [errors, setErrors] = useState<Errors>({});
  const formRef = useRef<HTMLFormElement>(null);

  const fieldOptions = useMemo(
    () => FIELDS_OF_STUDY.map((f) => ({ value: f, label: f })),
    [],
  );
  const universityOptions = useMemo(
    () => UNIVERSITIES.map((u) => ({ value: u, label: u })),
    [],
  );

  function validate(): Errors {
    const next: Errors = {};

    // Every message names the field and says what a good answer looks like.
    // The previous set ("Required", "Must be 0-9") told a user that something
    // was wrong without telling them what would be right.
    if (!formData.degree) next.degree = "Select the degree you hold or are studying for.";
    if (!formData.major.trim()) {
      next.major = "Enter your major — for example, Computer Science.";
    }
    if (!formData.university.trim()) {
      next.university = "Enter the institution that awarded (or will award) it.";
    }

    if (!formData.gradYear) {
      next.gradYear = "Enter the year you graduated, or expect to.";
    } else {
      const year = parseInt(formData.gradYear, 10);
      if (Number.isNaN(year)) {
        next.gradYear = "Enter a four-digit year, e.g. 2026.";
      } else if (year < MIN_GRAD_YEAR || year > MAX_GRAD_YEAR) {
        next.gradYear = `Enter a year between ${MIN_GRAD_YEAR} and ${MAX_GRAD_YEAR}.`;
      }
    }

    if (!formData.gpa.trim()) {
      next.gpa = "Enter your GPA so we can check it against entry requirements.";
    } else {
      const max = formData.gpaScale === "4.0" ? 4 : 100;
      const gpa = Number(formData.gpa);
      if (Number.isNaN(gpa)) {
        next.gpa = "Enter a number, e.g. 3.4.";
      } else if (gpa < 0 || gpa > max) {
        next.gpa = `On the ${formData.gpaScale === "4.0" ? "4.0" : "100"} scale, that should be between 0 and ${max}.`;
      }
    }

    if (!formData.ects.trim()) {
      next.ects = "Enter your total credits — a Bachelor's is usually 180 or 240.";
    } else {
      const ects = Number(formData.ects);
      if (Number.isNaN(ects) || ects < 0) {
        next.ects = "Enter a whole number of credits, e.g. 180.";
      } else if (ects > 600) {
        next.ects = "That looks too high — ECTS totals are usually under 400.";
      }
    }

    return next;
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const nextErrors = validate();
    setErrors(nextErrors);
    if (Object.keys(nextErrors).length === 0) {
      onNext(formData);
      return;
    }
    // Bring the first invalid field into view -- with six fields and a short
    // viewport, several errors can render off-screen below the fold, which
    // previously read as a dead Continue button (BUG-048).
    requestAnimationFrame(() => {
      formRef.current
        ?.querySelector<HTMLElement>("[aria-invalid='true']")
        ?.scrollIntoView({ behavior: "smooth", block: "center" });
    });
  }

  function set<K extends keyof AcademicData>(key: K, value: AcademicData[K]) {
    setFormData((prev) => ({ ...prev, [key]: value }));
    if (errors[key]) setErrors((prev) => ({ ...prev, [key]: undefined }));
  }

  return (
    <form ref={formRef} onSubmit={handleSubmit} noValidate className="flex flex-col gap-5">
      <div>
        <Heading as="h2" size="md">
          Tell us about your education
        </Heading>
        <Text size="sm" tone="muted" className="mt-1">
          We use this to match you with programmes that fit your background.
        </Text>
      </div>

      <Field label="Degree level" required error={errors.degree}>
        <Select
          name="degree"
          placeholder="Select your degree"
          value={formData.degree}
          onChange={(e) => set("degree", e.target.value)}
        >
          {DEGREE_LEVELS.map((level) => (
            <option key={level.value} value={level.value}>
              {level.label}
            </option>
          ))}
        </Select>
      </Field>

      <Field
        label="Major / field of study"
        required
        error={errors.major}
        hint="Start typing to search. Not listed? Type your own and press Enter."
      >
        <Combobox
          name="major"
          options={fieldOptions}
          value={formData.major}
          onChange={(v) => set("major", v)}
          allowCustomValue
          placeholder="e.g. Computer Science"
        />
      </Field>

      <Field
        label="Institution / university"
        required
        error={errors.university}
        hint="Not listed? Type the full name and press Enter."
      >
        <Combobox
          name="university"
          options={universityOptions}
          value={formData.university}
          onChange={(v) => set("university", v)}
          allowCustomValue
          placeholder="e.g. Cairo University"
        />
      </Field>

      <Field label="Graduation year (or expected)" required error={errors.gradYear}>
        <Input
          type="number"
          name="gradYear"
          inputMode="numeric"
          min={MIN_GRAD_YEAR}
          max={MAX_GRAD_YEAR}
          placeholder={`e.g. ${CURRENT_YEAR + 1}`}
          value={formData.gradYear}
          onChange={(e) => set("gradYear", e.target.value)}
        />
      </Field>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-[1fr_auto] sm:items-start">
        <Field label="GPA" required error={errors.gpa}>
          <Input
            type="number"
            name="gpa"
            inputMode="decimal"
            step="0.01"
            min={0}
            max={formData.gpaScale === "4.0" ? 4 : 100}
            placeholder={formData.gpaScale === "4.0" ? "e.g. 3.8" : "e.g. 85"}
            value={formData.gpa}
            onChange={(e) => set("gpa", e.target.value)}
          />
        </Field>

        <Field label="Scale">
          <Select
            selectSize="md"
            value={formData.gpaScale}
            onChange={(e) => {
              // Re-validate the GPA against the new ceiling: switching from
              // /100 to /4.0 with 85 in the box left a stale "valid" state.
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

      <Field
        label="ECTS credits"
        required
        error={errors.ects}
        hint="Total credits earned so far. A Bachelor's is typically 180–240."
      >
        <Input
          type="number"
          name="ECTScred"
          inputMode="numeric"
          min={0}
          placeholder="e.g. 180"
          value={formData.ects}
          onChange={(e) => set("ects", e.target.value)}
        />
      </Field>

      <Button type="submit" size="lg" fullWidth trailingIcon={ArrowRight} className="mt-2">
        Continue
      </Button>
    </form>
  );
}
