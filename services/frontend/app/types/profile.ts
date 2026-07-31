// Mirrors the User service's response shape for GET /users/:id (users.controller.ts
// findOneWithProfile), proxied through the Gateway at GET /api/profile.

export interface UserProfileDetail {
  userId: string;
  degreeLevel: string | null;
  gpa: number | null;
  ieltsScore: number | null;
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
