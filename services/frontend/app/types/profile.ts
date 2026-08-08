// Mirrors the User service's response shape for GET /users/:id (users.controller.ts
// findOneWithProfile), proxied through the Gateway at GET /api/profile.

export interface UserProfileDetail {
  userId: string;
  degreeLevel: string | null;
  gpa: number | null;
  ieltsScore: number | null;
  ieltsListening: number | null;
  ieltsReading: number | null;
  ieltsWriting: number | null;
  ieltsSpeaking: number | null;
  targetCountries: string[];
  fieldOfStudy: string | null;
  ects: number | null;
  workExperienceYears: number;
  extracurricularsScore: number;
  gpaScale: "4.0" | "100";
}

export interface CurrentUser {
  id: string;
  email: string;
  subscriptionTier: "free" | "paid";
  isVerified: boolean;
  profile: UserProfileDetail | null;
}

/**
 * True once the user has entered at least one piece of the data the
 * onboarding wizard collects. Registration already creates a UserProfile
 * row (users.service.ts) with every collectible field left null/empty, so
 * `profile` itself is never null after signup -- checking for that would
 * never route anyone into onboarding. This checks the fields onboarding
 * actually writes (buildProfilePayload in app/onboarding/page.tsx) instead.
 */
export function isProfileComplete(profile: UserProfileDetail | null): boolean {
  if (!profile) return false;
  return (
    profile.degreeLevel !== null ||
    profile.fieldOfStudy !== null ||
    profile.gpa !== null ||
    profile.ieltsScore !== null ||
    profile.targetCountries.length > 0
  );
}
