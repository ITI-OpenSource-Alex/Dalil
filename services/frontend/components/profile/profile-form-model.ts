import type { UpdateProfilePayload } from "@/lib/api";
import {
  computeOverallBand,
  formatBand,
  isValidBand,
  parseBand,
} from "@/lib/ielts";
import type { UserProfileDetail } from "@/app/types/profile";

export interface ProfileFormValues {
  degreeLevel: string;
  fieldOfStudy: string;
  targetFieldOfStudy: string;
  gpa: string;
  gpaScale: "4.0" | "100";
  ects: string;
  ieltsListening: string;
  ieltsReading: string;
  ieltsWriting: string;
  ieltsSpeaking: string;
  ieltsScore: string;
  overrideOverall: boolean;
  workExperienceYears: string;
  extracurricularsScore: string;
  targetCountries: string[];
}

type Errors = Partial<Record<keyof ProfileFormValues, string>>;

export function valuesFromProfile(
  profile: UserProfileDetail | null,
): ProfileFormValues {
  const ieltsListening =
    profile?.ieltsListening != null ? String(profile.ieltsListening) : "";
  const ieltsReading =
    profile?.ieltsReading != null ? String(profile.ieltsReading) : "";
  const ieltsWriting =
    profile?.ieltsWriting != null ? String(profile.ieltsWriting) : "";
  const ieltsSpeaking =
    profile?.ieltsSpeaking != null ? String(profile.ieltsSpeaking) : "";
  const ieltsScore =
    profile?.ieltsScore != null ? String(profile.ieltsScore) : "";

  const computed = computeOverallBand({
    listening: parseBand(ieltsListening),
    reading: parseBand(ieltsReading),
    writing: parseBand(ieltsWriting),
    speaking: parseBand(ieltsSpeaking),
  });
  const overall = parseBand(ieltsScore);
  const overrideOverall =
    overall !== null && (computed === null || computed !== overall);

  return {
    degreeLevel: profile?.degreeLevel ?? "",
    fieldOfStudy: profile?.fieldOfStudy ?? "",
    targetFieldOfStudy:
      profile?.targetFieldOfStudy ?? profile?.fieldOfStudy ?? "",
    gpa: profile?.gpa != null ? String(profile.gpa) : "",
    gpaScale: profile?.gpaScale ?? "4.0",
    ects: profile?.ects != null ? String(profile.ects) : "",
    ieltsListening,
    ieltsReading,
    ieltsWriting,
    ieltsSpeaking,
    ieltsScore:
      !overrideOverall && computed !== null ? formatBand(computed) : ieltsScore,
    overrideOverall,
    workExperienceYears:
      profile?.workExperienceYears != null
        ? String(profile.workExperienceYears)
        : "",
    extracurricularsScore:
      profile?.extracurricularsScore != null
        ? String(profile.extracurricularsScore)
        : "",
    targetCountries: profile?.targetCountries ?? [],
  };
}

function bandFieldError(value: string, label: string): string | undefined {
  if (!value.trim()) return undefined;
  const num = Number(value);
  if (Number.isNaN(num)) return `Enter a ${label} band between 0 and 9.`;
  if (num < 0 || num > 9) return "Bands run from 0 to 9.";
  if (!isValidBand(num)) return "Bands go in half steps — 6.5, not 6.4.";
  return undefined;
}

export function validateProfile(values: ProfileFormValues): Errors {
  const errors: Errors = {};

  if (values.gpa.trim()) {
    const gpa = Number(values.gpa);
    const max = values.gpaScale === "4.0" ? 4 : 100;
    if (Number.isNaN(gpa)) errors.gpa = "Enter a number, e.g. 3.4.";
    else if (gpa < 0 || gpa > max) {
      errors.gpa = `On the ${values.gpaScale} scale, that should be between 0 and ${max}.`;
    }
  }

  if (values.ects.trim()) {
    const ects = Number(values.ects);
    if (Number.isNaN(ects) || ects < 0) {
      errors.ects = "Enter a whole number of credits, e.g. 180.";
    } else if (ects > 600) {
      errors.ects = "That looks too high — ECTS totals are usually under 400.";
    }
  }

  const listeningErr = bandFieldError(values.ieltsListening, "Listening");
  if (listeningErr) errors.ieltsListening = listeningErr;
  const readingErr = bandFieldError(values.ieltsReading, "Reading");
  if (readingErr) errors.ieltsReading = readingErr;
  const writingErr = bandFieldError(values.ieltsWriting, "Writing");
  if (writingErr) errors.ieltsWriting = writingErr;
  const speakingErr = bandFieldError(values.ieltsSpeaking, "Speaking");
  if (speakingErr) errors.ieltsSpeaking = speakingErr;

  if (values.ieltsScore.trim()) {
    const band = Number(values.ieltsScore);
    if (Number.isNaN(band)) errors.ieltsScore = "Enter a band between 0 and 9.";
    else if (band < 0 || band > 9) errors.ieltsScore = "Bands run from 0 to 9.";
    else if (!isValidBand(band)) {
      errors.ieltsScore = "Bands go in half steps — 6.5, not 6.4.";
    }
  }

  if (values.workExperienceYears.trim()) {
    const years = Number(values.workExperienceYears);
    if (!Number.isInteger(years) || years < 0) {
      errors.workExperienceYears = "Enter a whole number of years, e.g. 2.";
    } else if (years > 60) {
      errors.workExperienceYears =
        "That looks too high — enter years, not months.";
    }
  }

  if (values.extracurricularsScore.trim()) {
    const score = Number(values.extracurricularsScore);
    if (!Number.isInteger(score) || score < 0 || score > 10) {
      errors.extracurricularsScore = "Rate your activities from 0 to 10.";
    }
  }

  return errors;
}

/**
 * Builds the PUT body.
 *
 * Every field is optional in UpdateProfileDto, so an emptied box is sent as an
 * omission rather than as null — the backend has no "clear this field"
 * semantics, and inventing one client-side by sending 0 would be worse than
 * leaving the old value in place.
 */
export function payloadFromValues(
  values: ProfileFormValues,
): UpdateProfilePayload {
  const payload: UpdateProfilePayload = {};

  if (values.degreeLevel) payload.degreeLevel = values.degreeLevel;
  if (values.fieldOfStudy.trim())
    payload.fieldOfStudy = values.fieldOfStudy.trim();
  if (values.targetFieldOfStudy.trim()) {
    payload.targetFieldOfStudy = values.targetFieldOfStudy.trim();
  }

  if (values.gpa.trim()) {
    payload.gpa = Number(values.gpa);
    payload.gpaScale = values.gpaScale;
  }
  if (values.ects.trim()) payload.ects = Number(values.ects);

  const listening = parseBand(values.ieltsListening);
  if (listening !== null) payload.ieltsListening = listening;
  const reading = parseBand(values.ieltsReading);
  if (reading !== null) payload.ieltsReading = reading;
  const writing = parseBand(values.ieltsWriting);
  if (writing !== null) payload.ieltsWriting = writing;
  const speaking = parseBand(values.ieltsSpeaking);
  if (speaking !== null) payload.ieltsSpeaking = speaking;

  // Prefer the computed overall when the user hasn't overridden it, so a
  // section-band commit that races the sync effect still persists the right
  // ieltsScore (the field programme matching gates on).
  let band = parseBand(values.ieltsScore);
  if (!values.overrideOverall) {
    const computed = computeOverallBand({
      listening,
      reading,
      writing,
      speaking,
    });
    if (computed !== null) band = computed;
  }
  if (band !== null) payload.ieltsScore = band;

  if (values.workExperienceYears.trim()) {
    payload.workExperienceYears = Number(values.workExperienceYears);
  }
  if (values.extracurricularsScore.trim()) {
    payload.extracurricularsScore = Number(values.extracurricularsScore);
  }

  payload.targetCountries = values.targetCountries;

  return payload;
}

/** Optimistic UI patch from the current form values. */
export function parsedDetailFromValues(
  values: ProfileFormValues,
): Partial<UserProfileDetail> {
  const payload = payloadFromValues(values);
  return {
    ...(payload.degreeLevel !== undefined
      ? { degreeLevel: payload.degreeLevel }
      : {}),
    ...(payload.fieldOfStudy !== undefined
      ? { fieldOfStudy: payload.fieldOfStudy }
      : {}),
    ...(payload.targetFieldOfStudy !== undefined
      ? { targetFieldOfStudy: payload.targetFieldOfStudy }
      : {}),
    ...(payload.gpa !== undefined ? { gpa: payload.gpa } : {}),
    ...(payload.gpaScale !== undefined ? { gpaScale: payload.gpaScale } : {}),
    ...(payload.ects !== undefined ? { ects: payload.ects } : {}),
    ...(payload.ieltsListening !== undefined
      ? { ieltsListening: payload.ieltsListening }
      : {}),
    ...(payload.ieltsReading !== undefined
      ? { ieltsReading: payload.ieltsReading }
      : {}),
    ...(payload.ieltsWriting !== undefined
      ? { ieltsWriting: payload.ieltsWriting }
      : {}),
    ...(payload.ieltsSpeaking !== undefined
      ? { ieltsSpeaking: payload.ieltsSpeaking }
      : {}),
    ...(payload.ieltsScore !== undefined
      ? { ieltsScore: payload.ieltsScore }
      : {}),
    ...(payload.workExperienceYears !== undefined
      ? { workExperienceYears: payload.workExperienceYears }
      : {}),
    ...(payload.extracurricularsScore !== undefined
      ? { extracurricularsScore: payload.extracurricularsScore }
      : {}),
    targetCountries: payload.targetCountries ?? values.targetCountries,
  };
}
