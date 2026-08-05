"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { CheckCircle2, ShieldCheck } from "lucide-react";
import { authApi, apiErrorMessage, type UpdateProfilePayload } from "@/lib/api";
import { subscriptionErrorFromAxios } from "@/lib/subscription";
import { parseBand } from "@/lib/ielts";
import { DURATION, EASE } from "@/lib/motion";
import { Alert, Button, Card, Icon, Skeleton, Text } from "@/components/ui";
import { Wordmark } from "@/components/marketing/wordmark";
import { OnboardingStepper, ONBOARDING_STEPS } from "@/components/onboarding/onboarding-stepper";
import AcademicStep from "@/components/onboarding/AcademicStep";
import LanguageStep from "@/components/onboarding/LanguageStep";
import TargetsStep from "@/components/onboarding/TargetStep";
import CvUploadStep from "@/components/onboarding/CvUploadStep";
import {
  EMPTY_DRAFT,
  clearDraft,
  loadDraft,
  saveDraft,
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
export function buildProfilePayload(
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
    // parseBand, not parseNumber: only a reportable band reaches the profile.
    // `ieltsScore` is what RAG's hard gate compares against `min_ielts`, so a
    // value like 6.4 slipping through would silently mis-gate every programme.
    const overall = parseBand(language.overallScore);
    if (overall !== null) payload.ieltsScore = overall;
  }

  if (targets.destinations.length > 0) payload.targetCountries = targets.destinations;

  return payload;
}

function OnboardingWizard() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const prefersReduced = useReducedMotion();

  // The step lives in the URL (?step=2) so refreshing or navigating back
  // doesn't silently drop the user's place in the wizard the way in-memory-only
  // state did before.
  const stepParam = Number(searchParams.get("step"));
  const requestedStep = stepParam >= 1 && stepParam <= TOTAL_STEPS ? stepParam : 1;

  // Draft answers are restored from sessionStorage on mount rather than being
  // seeded into useState directly: reading storage during render is a hydration
  // mismatch (the server has no sessionStorage), so the first paint uses the
  // empty shapes and the effect below fills them in.
  const [draft, setDraft] = useState(EMPTY_DRAFT);
  const [restored, setRestored] = useState(false);
  const [finishing, setFinishing] = useState(false);
  const [finishError, setFinishError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  useEffect(() => {
    setDraft(loadDraft());
    setRestored(true);
  }, []);

  useEffect(() => {
    if (restored) saveDraft(draft);
  }, [draft, restored]);

  // A deep link to ?step=3 with nothing filled in strands the user on a step
  // whose Back button leads to answers they never gave. Clamp forward
  // navigation to one past the furthest step that actually has data.
  const furthestAnswered =
    draft.targets.destinations.length > 0
      ? 4
      : draft.language.hasTakenIelts
        ? 3
        : draft.academic.degree
          ? 2
          : 1;
  const currentStep = restored
    ? Math.min(requestedStep, furthestAnswered)
    : requestedStep;

  const goToStep = useCallback(
    (step: number) => {
      router.push(`/onboarding?step=${step}`, { scroll: false });
      // The card can be taller than the viewport on a phone; landing on step 3
      // scrolled halfway down it otherwise.
      window.scrollTo({ top: 0, behavior: prefersReduced ? "auto" : "smooth" });
    },
    [router, prefersReduced],
  );

  async function handleFinish(_cv: { fileName: string; skipped: boolean } | null) {
    setFinishError(null);
    setFinishing(true);
    try {
      const payload = buildProfilePayload(draft.academic, draft.language, draft.targets);
      // Only call the network at all if there's something to persist -- an
      // entirely skipped wizard shouldn't produce a spinner and a PUT with an
      // empty body.
      if (Object.keys(payload).length > 0) {
        await authApi.updateProfile(payload);
      }
      clearDraft();
      setDone(true);
      // A hard navigation so the newly-written profile is read fresh: the
      // sidebar's "Complete Profile" nudge is driven by GET /api/profile, and
      // a client-side push would leave the pre-onboarding response cached.
      setTimeout(() => {
        window.location.assign("/opportunities");
      }, 1100);
    } catch (err) {
      // The bug this replaces: handleFinish previously discarded the wizard's
      // data unconditionally. On failure here the data stays on screen (state
      // is untouched) and the user can retry rather than silently losing four
      // steps of input.
      const paid = subscriptionErrorFromAxios(err);
      setFinishError(
        paid
          ? "Saving your profile needs a moment — please try again."
          : (apiErrorMessage(err) ??
            "Could not save your profile. Your answers are still here — please try again."),
      );
      setFinishing(false);
    }
  }

  if (done) {
    return (
      <Card variant="raised" padding="lg" className="w-full max-w-xl">
        <div className="flex flex-col items-center gap-3 py-6 text-center" role="status">
          <span className="flex h-14 w-14 items-center justify-center rounded-full bg-success-subtle text-success">
            <Icon icon={CheckCircle2} size="lg" />
          </span>
          <p className="text-lg font-semibold text-fg">You&apos;re all set</p>
          <p className="text-sm leading-6 text-fg-muted">
            Finding programmes that match your profile&hellip;
          </p>
        </div>
      </Card>
    );
  }

  if (!restored) {
    // A real skeleton of the card that is about to appear, rather than a
    // centred spinner: the previous fallback changed the page's height and
    // shifted the wordmark as it resolved.
    return (
      <Card variant="raised" padding="lg" className="w-full max-w-xl">
        <div aria-busy="true" aria-label="Loading onboarding" className="space-y-6">
          <Skeleton className="h-2 w-full" />
          <div className="space-y-2">
            <Skeleton className="h-6 w-2/3" />
            <Skeleton className="h-4 w-full" />
          </div>
          <div className="space-y-4">
            <Skeleton className="h-11 w-full" />
            <Skeleton className="h-11 w-full" />
            <Skeleton className="h-11 w-full" />
          </div>
        </div>
      </Card>
    );
  }

  // Direction drives the slide: forward steps enter from the right, Back
  // enters from the left, so the motion matches the user's mental model of
  // moving through a sequence instead of every step arriving identically.
  const enterX = prefersReduced ? 0 : 32;

  return (
    <Card variant="raised" padding="lg" className="w-full max-w-xl overflow-hidden">
      <OnboardingStepper currentStep={currentStep} onStepSelect={goToStep} />

      {finishError && (
        <Alert tone="danger" announce="assertive" className="mb-6">
          {finishError}
        </Alert>
      )}

      <AnimatePresence mode="wait" initial={false}>
        <motion.div
          key={currentStep}
          initial={{ opacity: 0, x: enterX }}
          animate={{ opacity: 1, x: 0 }}
          exit={{ opacity: 0, x: -enterX }}
          transition={{ duration: DURATION.base, ease: EASE.out }}
        >
          {currentStep === 1 && (
            <AcademicStep
              initialData={draft.academic}
              onNext={(data) => {
                setDraft((prev) => ({ ...prev, academic: data }));
                goToStep(2);
              }}
            />
          )}
          {currentStep === 2 && (
            <LanguageStep
              initialData={draft.language}
              onNext={(data) => {
                setDraft((prev) => ({ ...prev, language: data }));
                goToStep(3);
              }}
              onBack={() => goToStep(1)}
            />
          )}
          {currentStep === 3 && (
            <TargetsStep
              initialData={draft.targets}
              onNext={(data) => {
                setDraft((prev) => ({ ...prev, targets: data }));
                goToStep(4);
              }}
              onBack={() => goToStep(2)}
            />
          )}
          {currentStep === 4 && (
            <CvUploadStep
              onComplete={handleFinish}
              onBack={() => goToStep(3)}
              finishing={finishing}
            />
          )}
        </motion.div>
      </AnimatePresence>

      <p className="mt-6 flex items-start gap-2 border-t border-border pt-4 text-xs leading-5 text-fg-subtle">
        <Icon icon={ShieldCheck} size="xs" className="mt-0.5 shrink-0" />
        <span>
          Your answers are saved as you go and only used to match you with
          programmes. You can change any of this later from your profile.
        </span>
      </p>
    </Card>
  );
}

export default function OnboardingWizardPage() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-8 bg-canvas px-4 py-8 sm:py-12">
      <Link href="/" className="rounded-chip">
        <Wordmark />
        <span className="sr-only">home</span>
      </Link>

      <Suspense
        fallback={
          <Card variant="raised" padding="lg" className="w-full max-w-xl">
            <div className="space-y-6" aria-busy="true" aria-label="Loading onboarding">
              <Skeleton className="h-2 w-full" />
              <Skeleton className="h-6 w-2/3" />
              <Skeleton className="h-11 w-full" />
              <Skeleton className="h-11 w-full" />
            </div>
          </Card>
        }
      >
        <OnboardingWizard />
      </Suspense>

      <Text size="sm" tone="subtle">
        Rather do this later?{" "}
        <Button variant="link" size="sm" asChild>
          <Link href="/chat">Skip to GOA</Link>
        </Button>
      </Text>
    </div>
  );
}
