"use client";

import React, {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
} from "react";
import Link from "next/link";
import { ArrowRight, Check, Sparkles } from "lucide-react";
import {
  DEFAULT_UPGRADE_URL,
  isSubscriptionRequiredError,
  paidFeatureCopy,
  type PaidFeatureId,
} from "@/lib/subscription";
import { Button, Icon, Modal, ModalContent, Text } from "@/components/ui";

/* ------------------------------------------------------------------ *
 * One upgrade dialog for the whole app.
 *
 * Mounted once in the authenticated shell and reached through
 * `useUpgradePrompt()`, so a paid-tier refusal renders identically whether it
 * came from the exam landing page, the CV step or a chat turn. The previous
 * behaviour — each call site inventing its own banner, or worse, printing the
 * Gateway's JSON — is what item 6 of this work was about.
 * ------------------------------------------------------------------ */

interface UpgradePromptState {
  feature?: PaidFeatureId;
  upgradeUrl: string;
}

interface UpgradeContextValue {
  /** Opens the dialog for a named feature. */
  show: (feature?: PaidFeatureId, upgradeUrl?: string) => void;
  /**
   * Opens the dialog if `error` is a paid-tier refusal and returns true;
   * returns false for anything else so the caller can handle a real fault.
   * This is the shape every call site actually wants:
   *
   *   catch (err) { if (!handle(err, "exam")) setError(genericMessage); }
   */
  handle: (error: unknown, feature?: PaidFeatureId) => boolean;
}

const UpgradeContext = createContext<UpgradeContextValue | null>(null);

/** Stable no-op used outside UpgradeProvider — must not be recreated per render. */
const UPGRADE_PROMPT_FALLBACK: UpgradeContextValue = {
  show: () => {},
  handle: () => false,
};

export function UpgradeProvider({ children }: { children: React.ReactNode }) {
  const [prompt, setPrompt] = useState<UpgradePromptState | null>(null);

  const show = useCallback((feature?: PaidFeatureId, upgradeUrl?: string) => {
    setPrompt({ feature, upgradeUrl: upgradeUrl || DEFAULT_UPGRADE_URL });
  }, []);

  const handle = useCallback(
    (error: unknown, feature?: PaidFeatureId) => {
      if (!isSubscriptionRequiredError(error)) return false;
      setPrompt({
        feature: error.feature ?? feature,
        upgradeUrl: error.upgradeUrl,
      });
      return true;
    },
    [],
  );

  const value = useMemo<UpgradeContextValue>(
    () => ({ show, handle }),
    [show, handle],
  );

  return (
    <UpgradeContext.Provider value={value}>
      {children}
      <UpgradeDialog
        open={prompt !== null}
        feature={prompt?.feature}
        upgradeUrl={prompt?.upgradeUrl ?? DEFAULT_UPGRADE_URL}
        onOpenChange={(next) => {
          if (!next) setPrompt(null);
        }}
      />
    </UpgradeContext.Provider>
  );
}

/**
 * Falls back to a no-op outside the provider rather than throwing. A missing
 * provider should not be able to crash a page whose only sin is calling this
 * defensively — it degrades to the caller's own error handling instead.
 */
export function useUpgradePrompt(): UpgradeContextValue {
  const context = useContext(UpgradeContext);
  return context ?? UPGRADE_PROMPT_FALLBACK;
}

export function UpgradeDialog({
  open,
  onOpenChange,
  feature,
  upgradeUrl,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  feature?: PaidFeatureId;
  upgradeUrl: string;
}) {
  const copy = paidFeatureCopy(feature);
  // An absolute URL means the Gateway named a billing host; anything else is
  // an in-app route and should be a client-side navigation.
  const isExternal = /^https?:\/\//i.test(upgradeUrl);

  return (
    <Modal open={open} onOpenChange={onOpenChange}>
      <ModalContent
        title={copy.title}
        description={copy.description}
        size="md"
        footer={
          <>
            <Button variant="ghost" onClick={() => onOpenChange(false)}>
              Not now
            </Button>
            {isExternal ? (
              <Button asChild trailingIcon={ArrowRight}>
                <a href={upgradeUrl} target="_blank" rel="noopener noreferrer">
                  Upgrade to Dalil Pro
                </a>
              </Button>
            ) : (
              <Button asChild trailingIcon={ArrowRight}>
                <Link href={upgradeUrl} onClick={() => onOpenChange(false)}>
                  Upgrade to Dalil Pro
                </Link>
              </Button>
            )}
          </>
        }
      >
        <div className="flex flex-col gap-5">
          <div className="flex items-center gap-2 rounded-panel border border-brand-border bg-brand-subtle px-3.5 py-2.5">
            <Icon icon={Sparkles} size="sm" className="shrink-0 text-brand-fg" />
            <Text size="sm" className="font-semibold text-brand-fg">
              Dalil Pro
            </Text>
          </div>

          <div>
            <Text size="sm" tone="muted" className="mb-3 font-semibold">
              What you unlock
            </Text>
            <ul className="flex flex-col gap-2.5">
              {copy.benefits.map((benefit) => (
                <li key={benefit} className="flex items-start gap-2.5">
                  <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-success-subtle text-success-fg">
                    <Icon icon={Check} size="xs" />
                  </span>
                  <Text size="sm">{benefit}</Text>
                </li>
              ))}
            </ul>
          </div>

          <Text size="sm" tone="subtle">
            Nothing you have already done is affected — your profile, matched
            programmes and checklists stay on the Free plan.
          </Text>
        </div>
      </ModalContent>
    </Modal>
  );
}
