"use client";

import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { CheckCircle2 } from "lucide-react";
import { authApi, apiErrorMessage, type UpdateProfilePayload } from "@/lib/api";
import { Alert, Button, Card, Icon } from "@/components/ui";
import { Wordmark } from "@/components/marketing/wordmark";
import { OnboardingStepper, ONBOARDING_STEPS } from "@/components/onboarding/onboarding-stepper";
import AcademicStep from "@/components/onboarding/AcademicStep";
import LanguageStep from "@/components/onboarding/LanguageStep";
import TargetsStep from "@/components/onboarding/TargetStep";
import CvUploadStep from "@/components/onboarding/CvUploadStep";
import {
  EMPTY_ACADEMIC,
  EMPTY_LANGUAGE,
  EMPTY_TARGETS,
  type AcademicData,
  type LanguageData,
  type TargetsData,
} from "@/components/onboarding/types";

const TOTAL_STEPS = ONBOARDING_STEPS.length;

function parseNumber(value: string): number | undefined {
  const num = Number(value);
  return value.trim() !== "" && !Number.isNaN(num) ? num : undefined;
}

/**
 * Builds the payload for PUT /api/profile from whatever the wizard collected.
 * Not every field the wizard asks for has a home in UpdateProfileDto
 * (services/user/src/profile/dto/update-profile.dto.ts) -- university,
 * graduation year, target degree/major/intake, and the "planning to take
 * IELTS" target score have no backend field to land in. Those stay in the
 * wizard's own state (useful context within the session) but are not sent;
 * this is a real backend-schema gap, flagged rather than papered over. See
 * docs/FRONTEND-REDESIGN-PLAN.md §16.5.
 */
function buildProfilePayload(
  academic: AcademicData,
  language: LanguageData,
  targets: TargetsData,
): UpdateProfilePayload {
  const payload: UpdateProfilePayload = {};

  if (academic.degree) payload.degreeLevel = academic.degree;
  if (academic.major.trim()) payload.fieldOfStudy = academic.major.trim();
  const gpa = parseNumber(academic.gpa);
  if (gpa !== undefined) {
    payload.gpa = gpa;
    payload.gpaScale = academic.gpaScale;
  }
  const ects = parseNumber(academic.ects);
  if (ects !== undefined) payload.ects = ects;

  if (language.hasTakenIelts === "yes") {
    const overall = parseNumber(language.overallScore);
    if (overall !== undefined) payload.ieltsScore = overall;
  }

  if (targets.destinations.length > 0) payload.targetCountries = targets.destinations;

  return payload;
}

function OnboardingWizard() {
  const router = useRouter();
  const searchParams = useSearchParams();

  // The step lives in the URL (?step=2) so refreshing or navigating back
  // doesn't silently drop the user's place in the wizard the way in-memory-only
  // state did before.
  const stepParam = Number(searchParams.get("step"));
  const currentStep = stepParam >= 1 && stepParam <= TOTAL_STEPS ? stepParam : 1;

  const [academic, setAcademic] = useState<AcademicData>(EMPTY_ACADEMIC);
  const [language, setLanguage] = useState<LanguageData>(EMPTY_LANGUAGE);
  const [targets, setTargets] = useState<TargetsData>(EMPTY_TARGETS);
  const [finishing, setFinishing] = useState(false);
  const [finishError, setFinishError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  function goToStep(step: number) {
    router.push(`/onboarding?step=${step}`, { scroll: false });
  }

  async function handleFinish(cv: { fileName: string; skipped: boolean } | null) {
    setFinishError(null);
    setFinishing(true);
    try {
      const payload = buildProfilePayload(academic, language, targets);
      // Only call the network at all if there's something to persist -- an
      // entirely skipped wizard shouldn't produce a spinner and a PUT with an
      // empty body.
      if (Object.keys(payload).length > 0) {
        await authApi.updateProfile(payload);
      }
      setDone(true);
      setTimeout(() => router.push("/chat"), 1200);
    } catch (err) {
      // The bug this replaces: handleFinish previously discarded the wizard's
      // data unconditionally. On failure here the data stays on screen (state
      // is untouched) and the user can retry rather than silently losing four
      // steps of input.
      setFinishError(
        apiErrorMessage(err) ??
          "Could not save your profile. Your answers are still here — please try again.",
      );
    } finally {
      setFinishing(false);
    }
  }

  if (done) {
    return (
      <div className="flex flex-col items-center gap-3 py-6 text-center" role="status">
        <span className="flex h-14 w-14 items-center justify-center rounded-full bg-success-subtle text-success">
          <Icon icon={CheckCircle2} size="lg" />
        </span>
        <p className="text-lg font-semibold text-fg">You&apos;re all set</p>
        <p className="text-sm leading-6 text-fg-muted">Taking you to GOA&hellip;</p>
      </div>
    );
  }

  return (
    <Card variant="raised" padding="lg" className="w-full max-w-xl">
      <OnboardingStepper currentStep={currentStep} />

      {finishError && (
        <Alert tone="danger" announce="assertive" className="mb-6">
          {finishError}
        </Alert>
      )}

      {currentStep === 1 && (
        <AcademicStep
          initialData={academic}
          onNext={(data) => {
            setAcademic(data);
            goToStep(2);
          }}
        />
      )}
      {currentStep === 2 && (
        <LanguageStep
          initialData={language}
          onNext={(data) => {
            setLanguage(data);
            goToStep(3);
          }}
          onBack={() => goToStep(1)}
        />
      )}
      {currentStep === 3 && (
        <TargetsStep
          initialData={targets}
          onNext={(data) => {
            setTargets(data);
            goToStep(4);
          }}
          onBack={() => goToStep(2)}
        />
      )}
      {currentStep === 4 && (
        <CvUploadStep onComplete={handleFinish} onBack={() => goToStep(3)} finishing={finishing} />
      )}
    </Card>
  );
}

export default function OnboardingWizardPage() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-8 bg-canvas px-4 py-12">
      <Link href="/" className="rounded-chip">
        <Wordmark />
        <span className="sr-only">home</span>
      </Link>

      <Suspense
        fallback={
          <Card variant="raised" padding="lg" className="flex w-full max-w-xl justify-center">
            <Button variant="ghost" size="lg" loading loadingLabel="Loading onboarding">
              Loading
            </Button>
          </Card>
        }
      >
        <OnboardingWizard />
      </Suspense>
    </div>
  );
}
