"use client";

import { useCallback, useRef, useState } from "react";
import { authApi, apiErrorMessage } from "@/lib/api";
import type { UserProfileDetail } from "@/app/types/profile";
import {
  parsedDetailFromValues,
  payloadFromValues,
  validateProfile,
  type ProfileFormValues,
} from "./profile-form-model";

export type ProfileSaveState = "idle" | "saving" | "saved" | "error";
export type ProfileFieldErrors = Partial<
  Record<keyof ProfileFormValues, string>
>;

/**
 * Blur / commit autosave for the profile form.
 *
 * Saves the full current valid payload on each field commit. Skips when
 * validation fails or the payload matches the last successful save (avoids
 * loops from optimistic UI ↔ form sync).
 */
export function useProfileAutosave({
  getValues,
  onOptimisticUser,
  onSaveError,
  onSaved,
}: {
  getValues: () => ProfileFormValues;
  onOptimisticUser?: (partial: Partial<UserProfileDetail>) => void;
  onSaveError?: (message: string) => void;
  /** Fired after a PUT that actually changed something succeeded. */
  onSaved?: () => void;
}) {
  const lastSaved = useRef<string>("");
  const [saveState, setSaveState] = useState<ProfileSaveState>("idle");
  const [saveError, setSaveError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<ProfileFieldErrors>({});
  const inFlight = useRef(false);
  const pendingSave = useRef(false);

  const seedLastSaved = useCallback((values: ProfileFormValues) => {
    lastSaved.current = JSON.stringify(payloadFromValues(values));
    setFieldErrors({});
  }, []);

  const saveFromBlur = useCallback(async () => {
    if (inFlight.current) {
      pendingSave.current = true;
      return;
    }

    const values = getValues();
    const errors = validateProfile(values);
    setFieldErrors(errors);
    if (Object.keys(errors).length > 0) return;

    const payload = payloadFromValues(values);
    const fingerprint = JSON.stringify(payload);
    if (fingerprint === lastSaved.current) return;

    inFlight.current = true;
    setSaveState("saving");
    setSaveError(null);
    onOptimisticUser?.(parsedDetailFromValues(values));

    try {
      await authApi.updateProfile(payload);
      lastSaved.current = fingerprint;
      setSaveState("saved");
      onSaved?.();
    } catch (err) {
      const message =
        apiErrorMessage(err) ?? "Could not save your profile.";
      setSaveState("error");
      setSaveError(message);
      onSaveError?.(message);
    } finally {
      inFlight.current = false;
      if (pendingSave.current) {
        pendingSave.current = false;
        void saveFromBlur();
      }
    }
  }, [getValues, onOptimisticUser, onSaveError, onSaved]);

  return { saveState, saveError, fieldErrors, saveFromBlur, seedLastSaved };
}
