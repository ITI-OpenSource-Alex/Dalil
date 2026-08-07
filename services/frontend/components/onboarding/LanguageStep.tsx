"use client";

import { useState } from "react";
import { ArrowLeft, ArrowRight, Sparkles } from "lucide-react";
import { Alert, Button, Field, Heading, Input, Text } from "@/components/ui";
import { ChoiceCard } from "./choice-card";
import type { LanguageData } from "./types";

interface LanguageStepProps {
  onNext: (data: LanguageData) => void;
  onBack: () => void;
  initialData: LanguageData;
}

const SCORE_FIELDS = [
  { id: "listeningScore", label: "Listening" },
  { id: "readingScore", label: "Reading" },
  { id: "writingScore", label: "Writing" },
  { id: "speakingScore", label: "Speaking" },
] as const;

type Errors = Partial<Record<keyof LanguageData, string>>;

function validScore(value: string): boolean {
  const num = parseFloat(value);
  return !Number.isNaN(num) && num >= 0 && num <= 9 && (num * 2) % 1 === 0;
}

export default function LanguageStep({ onNext, onBack, initialData }: LanguageStepProps) {
  const [formData, setFormData] = useState<LanguageData>(initialData);
  const [errors, setErrors] = useState<Errors>({});

  function validate(): Errors {
    const next: Errors = {};

    if (!formData.hasTakenIelts) {
      next.hasTakenIelts = "Let us know whether you've taken IELTS.";
    } else if (formData.hasTakenIelts === "yes") {
      for (const field of SCORE_FIELDS) {
        const value = formData[field.id];
        if (!value) next[field.id] = "Required";
        else if (!validScore(value)) next[field.id] = "0-9 in 0.5 steps";
      }
      if (!formData.overallScore) next.overallScore = "Required";
      else if (!validScore(formData.overallScore)) next.overallScore = "0-9 in 0.5 steps";
    } else if (formData.hasTakenIelts === "no") {
      if (!formData.planningToTake) {
        next.planningToTake = "Let us know if you're planning to take it.";
      } else if (formData.planningToTake === "yes") {
        if (!formData.targetOverallScore) next.targetOverallScore = "Target score is required.";
        else {
          const num = parseFloat(formData.targetOverallScore);
          if (Number.isNaN(num) || num < 0 || num > 9) next.targetOverallScore = "Must be 0-9.";
        }
        if (!formData.targetExamDate) next.targetExamDate = "Target date is required.";
      }
    }

    return next;
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const nextErrors = validate();
    setErrors(nextErrors);
    if (Object.keys(nextErrors).length === 0) onNext(formData);
  }

  function setBranch(hasTakenIelts: LanguageData["hasTakenIelts"]) {
    setFormData((prev) => ({
      ...prev,
      hasTakenIelts,
      listeningScore: "",
      readingScore: "",
      writingScore: "",
      speakingScore: "",
      overallScore: "",
      planningToTake: "",
      targetOverallScore: "",
      targetExamDate: "",
    }));
    setErrors({});
  }

  function set<K extends keyof LanguageData>(key: K, value: LanguageData[K]) {
    setFormData((prev) => ({ ...prev, [key]: value }));
    if (errors[key]) setErrors((prev) => ({ ...prev, [key]: undefined }));
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-6">
      <div>
        <Heading as="h2" size="md">
          How&apos;s your English?
        </Heading>
        <Text size="sm" tone="muted" className="mt-1">
          We won&apos;t reject you for a low score — we&apos;ll explain the
          gap and plan around it.
        </Text>
      </div>

      <Field label="Have you taken IELTS before?" error={errors.hasTakenIelts}>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <ChoiceCard
            name="hasTakenIelts"
            value="yes"
            checked={formData.hasTakenIelts === "yes"}
            onChange={() => setBranch("yes")}
          >
            Yes, I have a score
          </ChoiceCard>
          <ChoiceCard
            name="hasTakenIelts"
            value="no"
            checked={formData.hasTakenIelts === "no"}
            onChange={() => setBranch("no")}
          >
            Not yet
          </ChoiceCard>
        </div>
      </Field>

      {formData.hasTakenIelts === "yes" && (
        <div className="flex flex-col gap-4 rounded-card border border-border bg-canvas-subtle p-4">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {SCORE_FIELDS.map((field) => (
              <Field key={field.id} label={field.label} error={errors[field.id]}>
                <Input
                  type="number"
                  name={field.id}
                  step={0.5}
                  inputMode="decimal"
                  placeholder="0.0"
                  value={formData[field.id]}
                  onChange={(e) => set(field.id, e.target.value)}
                />
              </Field>
            ))}
          </div>

          <Field label="Overall band score" error={errors.overallScore}>
            <Input
              type="number"
              name="overallScore"
              step={0.5}
              inputMode="decimal"
              placeholder="0.0"
              value={formData.overallScore}
              onChange={(e) => set("overallScore", e.target.value)}
              className="text-center text-base font-semibold"
            />
          </Field>
        </div>
      )}

      {formData.hasTakenIelts === "no" && (
        <div className="flex flex-col gap-4">
          <Field label="Planning to take it?" error={errors.planningToTake}>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <ChoiceCard
                name="planningToTake"
                value="yes"
                checked={formData.planningToTake === "yes"}
                onChange={() => set("planningToTake", "yes")}
              >
                Yes, planning to
              </ChoiceCard>
              <ChoiceCard
                name="planningToTake"
                value="no"
                checked={formData.planningToTake === "no"}
                onChange={() => set("planningToTake", "no")}
              >
                Not sure yet
              </ChoiceCard>
            </div>
          </Field>

          {formData.planningToTake === "yes" && (
            <div className="flex flex-col gap-4 rounded-card border border-border bg-canvas-subtle p-4">
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <Field label="Target overall score" error={errors.targetOverallScore}>
                  <Input
                    type="number"
                    name="targetOverallScore"
                    step={0.5}
                    inputMode="decimal"
                    placeholder="e.g. 7.5"
                    value={formData.targetOverallScore}
                    onChange={(e) => set("targetOverallScore", e.target.value)}
                  />
                </Field>
                <Field label="Target exam date" error={errors.targetExamDate}>
                  <Input
                    type="date"
                    name="targetExamDate"
                    value={formData.targetExamDate}
                    onChange={(e) => set("targetExamDate", e.target.value)}
                  />
                </Field>
              </div>

              <Alert tone="success" announce="none" icon={Sparkles}>
                We&apos;ll add IELTS preparation tasks to your checklist
                automatically.
              </Alert>
            </div>
          )}
        </div>
      )}

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
