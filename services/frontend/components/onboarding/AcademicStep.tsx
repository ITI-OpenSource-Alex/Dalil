"use client";

import { useRef, useState } from "react";
import { ArrowRight } from "lucide-react";
import { Button, Field, Heading, Input, Select, Text } from "@/components/ui";
import type { AcademicData } from "./types";

interface AcademicStepProps {
  onNext: (data: AcademicData) => void;
  initialData: AcademicData;
}

type Errors = Partial<Record<keyof AcademicData, string>>;

export default function AcademicStep({ onNext, initialData }: AcademicStepProps) {
  const [formData, setFormData] = useState<AcademicData>(initialData);
  const [errors, setErrors] = useState<Errors>({});
  const formRef = useRef<HTMLFormElement>(null);

  function validate(): Errors {
    const next: Errors = {};
    if (!formData.degree) next.degree = "Select your degree level.";
    if (!formData.major.trim()) next.major = "Enter your major or field of study.";
    if (!formData.university.trim()) next.university = "Enter your institution's name.";

    if (!formData.gradYear) {
      next.gradYear = "Graduation year is required.";
    } else {
      const year = parseInt(formData.gradYear, 10);
      if (Number.isNaN(year) || year < 1950 || year > 2035) {
        next.gradYear = "Enter a year between 1950 and 2035.";
      }
    }

    if (!formData.gpa.trim()) {
      next.gpa = "GPA is required.";
    } else {
      const max = formData.gpaScale === "4.0" ? 4 : 100;
      const gpa = Number(formData.gpa);
      if (Number.isNaN(gpa) || gpa < 0 || gpa > max) {
        next.gpa = `Enter a value between 0 and ${max}.`;
      }
    }

    if (!formData.ects.trim()) {
      next.ects = "ECTS credits are required.";
    } else if (Number.isNaN(Number(formData.ects)) || Number(formData.ects) < 0) {
      next.ects = "Enter a non-negative number.";
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
          <option value="Bachelors">Bachelor&apos;s degree</option>
          <option value="Masters">Master&apos;s degree</option>
          <option value="PhD">Ph.D. / Doctorate</option>
          <option value="Diploma">Diploma / Other</option>
        </Select>
      </Field>

      <Field label="Major / field of study" required error={errors.major}>
        <Input
          name="major"
          placeholder="e.g. Computer Science, Business Administration"
          value={formData.major}
          onChange={(e) => set("major", e.target.value)}
        />
      </Field>

      <Field label="Institution / university" required error={errors.university}>
        <Input
          name="university"
          placeholder="e.g. Stanford University"
          value={formData.university}
          onChange={(e) => set("university", e.target.value)}
        />
      </Field>

      <Field label="Graduation year (or expected)" required error={errors.gradYear}>
        <Input
          type="number"
          name="gradYear"
          inputMode="numeric"
          placeholder="e.g. 2026"
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
            placeholder={formData.gpaScale === "4.0" ? "e.g. 3.8" : "e.g. 85"}
            value={formData.gpa}
            onChange={(e) => set("gpa", e.target.value)}
          />
        </Field>

        <Field label="Scale">
          <Select
            selectSize="md"
            value={formData.gpaScale}
            onChange={(e) => set("gpaScale", e.target.value as "4.0" | "100")}
            className="sm:w-28"
          >
            <option value="4.0">/ 4.0</option>
            <option value="100">/ 100</option>
          </Select>
        </Field>
      </div>

      <Field label="ECTS credits" required error={errors.ects} hint="Total credits earned so far.">
        <Input
          type="number"
          name="ECTScred"
          inputMode="numeric"
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
