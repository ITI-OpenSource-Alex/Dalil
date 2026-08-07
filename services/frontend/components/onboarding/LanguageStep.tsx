"use client";

import { useEffect, useMemo, useState } from "react";
import { ArrowLeft, ArrowRight, Info, Pencil, RotateCcw, Sparkles } from "lucide-react";
import {
  bandDescriptor,
  computeOverallBand,
  formatBand,
  parseBand,
} from "@/lib/ielts";
import { Alert, Button, Field, Heading, Icon, Input, Text } from "@/components/ui";
import { ChoiceCard } from "./choice-card";
import { BandScoreInput, bandError } from "./ielts-score-input";
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

/** The earliest a candidate could sit an exam booked today. */
function todayISO(): string {
  return new Date().toISOString().slice(0, 10);
}

export default function LanguageStep({ onNext, onBack, initialData }: LanguageStepProps) {
  const [formData, setFormData] = useState<LanguageData>(initialData);
  const [errors, setErrors] = useState<Errors>({});

  const sections = useMemo(
    () => ({
      listening: parseBand(formData.listeningScore),
      reading: parseBand(formData.readingScore),
      writing: parseBand(formData.writingScore),
      speaking: parseBand(formData.speakingScore),
    }),
    [
      formData.listeningScore,
      formData.readingScore,
      formData.writingScore,
      formData.speakingScore,
    ],
  );

  const computedOverall = useMemo(() => computeOverallBand(sections), [sections]);

  /*
   * The overall band was previously a fifth number the candidate had to work
   * out and type. It is fully determined by the other four -- IELTS reports
   * the mean rounded to the nearest half band -- so asking for it was asking
   * someone to do arithmetic the form already knows the answer to, and
   * accepting whatever they typed meant a mistake there silently corrupted
   * the single field programme matching gates on (`min_ielts`).
   *
   * Kept in state rather than derived at submit time so the persisted draft
   * and the payload builder both see the same value without either having to
   * re-run the rounding rules.
   */
  useEffect(() => {
    if (formData.overrideOverall) return;
    const next = computedOverall === null ? "" : formatBand(computedOverall);
    if (next !== formData.overallScore) {
      setFormData((prev) => ({ ...prev, overallScore: next }));
    }
  }, [computedOverall, formData.overrideOverall, formData.overallScore]);

  const overallValue = parseBand(formData.overallScore);
  const overrideDiffers =
    formData.overrideOverall &&
    overallValue !== null &&
    computedOverall !== null &&
    overallValue !== computedOverall;

  function validate(): Errors {
    const next: Errors = {};

    if (!formData.hasTakenIelts) {
      next.hasTakenIelts = "Tell us whether you've sat IELTS — either answer is fine.";
      return next;
    }

    if (formData.hasTakenIelts === "yes") {
      for (const field of SCORE_FIELDS) {
        const error = bandError(formData[field.id], true);
        if (error) {
          next[field.id] =
            error === "Required" ? `Enter your ${field.label} band.` : error;
        }
      }
      const overallError = bandError(formData.overallScore, true);
      if (overallError) {
        next.overallScore =
          overallError === "Required"
            ? "Enter the overall band from your test report."
            : overallError;
      }
      return next;
    }

    if (!formData.planningToTake) {
      next.planningToTake = "Let us know if you're planning to take it.";
      return next;
    }

    if (formData.planningToTake === "yes") {
      const targetError = bandError(formData.targetOverallScore, true);
      if (targetError) {
        next.targetOverallScore =
          targetError === "Required"
            ? "Pick a band to aim for — most Master's programmes ask for 6.5."
            : targetError;
      }
      if (!formData.targetExamDate) {
        next.targetExamDate = "Roughly when do you plan to sit it?";
      } else if (formData.targetExamDate < todayISO()) {
        next.targetExamDate = "Choose a date in the future.";
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
    requestAnimationFrame(() => {
      document
        .querySelector<HTMLElement>('[role="alert"]')
        ?.scrollIntoView({ behavior: "smooth", block: "center" });
    });
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
      overrideOverall: false,
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
    <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-6">
      <div>
        <Heading as="h2" size="md">
          How&apos;s your English?
        </Heading>
        <Text size="sm" tone="muted" className="mt-1">
          We won&apos;t reject you for a low score — we&apos;ll explain the gap
          and plan around it.
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
        <div className="flex flex-col gap-5 rounded-card border border-border bg-canvas-subtle p-4 sm:p-5">
          <div className="flex items-start gap-2">
            <Icon icon={Info} size="sm" className="mt-0.5 shrink-0 text-fg-subtle" />
            <Text size="sm" tone="muted">
              Enter the four section bands from your test report. We&apos;ll work
              out your overall band for you.
            </Text>
          </div>

          {/* One per row rather than four across: the rail needs the full
              width to keep eleven tap targets above the 24px minimum, and a
              2x2 grid on a 360px phone put them at ~14px. */}
          <div className="flex flex-col gap-5">
            {SCORE_FIELDS.map((field) => (
              <BandScoreInput
                key={field.id}
                id={field.id}
                label={field.label}
                value={formData[field.id]}
                onChange={(v) => set(field.id, v)}
                error={errors[field.id]}
                compact
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
                  {formData.overrideOverall
                    ? "Entered manually"
                    : computedOverall === null
                      ? "Fill in all four sections above"
                      : "Calculated from your four sections"}
                </Text>
              </div>

              {formData.overrideOverall ? (
                <Input
                  type="number"
                  name="overallScore"
                  step={0.5}
                  min={0}
                  max={9}
                  inputMode="decimal"
                  aria-label="Overall band score"
                  value={formData.overallScore}
                  onChange={(e) => set("overallScore", e.target.value)}
                  invalid={Boolean(errors.overallScore)}
                  className="w-24 text-center text-base font-bold"
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

            {overallValue !== null && !formData.overrideOverall && (
              <Text size="sm" tone="muted" className="mt-2">
                {bandDescriptor(overallValue)}
              </Text>
            )}

            {errors.overallScore && (
              <p role="alert" className="mt-2 text-sm text-danger-fg">
                {errors.overallScore}
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
              {formData.overrideOverall ? (
                <Button
                  variant="link"
                  size="sm"
                  leadingIcon={RotateCcw}
                  onClick={() => {
                    set("overrideOverall", false);
                    setErrors((prev) => ({ ...prev, overallScore: undefined }));
                  }}
                >
                  Calculate it for me
                </Button>
              ) : (
                <Button
                  variant="link"
                  size="sm"
                  leadingIcon={Pencil}
                  onClick={() => set("overrideOverall", true)}
                >
                  My report says something different
                </Button>
              )}
            </div>
          </div>
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
            <div className="flex flex-col gap-5 rounded-card border border-border bg-canvas-subtle p-4 sm:p-5">
              <BandScoreInput
                id="targetOverallScore"
                label="Target overall band"
                value={formData.targetOverallScore}
                onChange={(v) => set("targetOverallScore", v)}
                error={errors.targetOverallScore}
              />

              <Field
                label="Target exam date"
                error={errors.targetExamDate}
                hint="An estimate is fine — it only shapes your checklist timeline."
              >
                <Input
                  type="date"
                  name="targetExamDate"
                  min={todayISO()}
                  value={formData.targetExamDate}
                  onChange={(e) => set("targetExamDate", e.target.value)}
                />
              </Field>

              <Alert tone="success" announce="none" icon={Sparkles}>
                We&apos;ll add IELTS preparation tasks to your checklist
                automatically.
              </Alert>
            </div>
          )}
        </div>
      )}

      <div className="flex flex-col-reverse gap-3 sm:flex-row">
        <Button
          type="button"
          variant="secondary"
          size="lg"
          leadingIcon={ArrowLeft}
          onClick={onBack}
        >
          Back
        </Button>
        <Button type="submit" size="lg" fullWidth trailingIcon={ArrowRight}>
          Continue
        </Button>
      </div>
    </form>
  );
}
