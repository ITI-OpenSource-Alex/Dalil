import axios from "axios";

// The Gateway. With no fallback this was `undefined`, which axios treats as
// "same origin" — so every auth call went to the Next.js server instead of the
// API and 404'd, with nothing to indicate a missing environment variable
// (BUG-045). Copy .env.example to .env.local to point at anything else.
const api = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8080",
  withCredentials: true,
});

export default api;

/**
 * Pulls a backend error message out of an axios error, in the shape both the
 * Gateway (fiber.Map{"message": ...}) and the User service (Nest's default
 * exception filter) actually send. Returns undefined for anything else
 * (network failure, unexpected shape) so callers can fall back to a generic,
 * honest message instead of printing "undefined".
 */
export function apiErrorMessage(err: unknown): string | undefined {
  if (
    typeof err === "object" &&
    err !== null &&
    "response" in err &&
    typeof (err as { response?: unknown }).response === "object"
  ) {
    const data = (err as { response?: { data?: unknown } }).response?.data;
    if (typeof data === "object" && data !== null && "message" in data) {
      const message = (data as { message?: unknown }).message;
      // class-validator's default filter sends `message` as a string[].
      if (Array.isArray(message)) return message.join(" ");
      if (typeof message === "string") return message;
    }
  }
  return undefined;
}

/** True when the response is the Gateway's paid-tier gate (subscription.go). */
export function isSubscriptionRequired(err: unknown): boolean {
  if (
    typeof err === "object" &&
    err !== null &&
    "response" in err &&
    typeof (err as { response?: unknown }).response === "object"
  ) {
    const response = (err as { response?: { status?: number; data?: unknown } }).response;
    const data = response?.data;
    return (
      response?.status === 403 &&
      typeof data === "object" &&
      data !== null &&
      "error" in data &&
      (data as { error?: unknown }).error === "subscription_required"
    );
  }
  return false;
}

export interface UpdateProfilePayload {
  degreeLevel?: string;
  gpa?: number;
  gpaScale?: "4.0" | "100";
  ieltsScore?: number;
  ielts_listening: number;
  ielts_reading: number;
  ielts_writing: number;
  ielts_speaking: number;
  targetCountries?: string[];
  fieldOfStudy?: string;
  ects?: number;
  workExperienceYears?: number;
  extracurricularsScore?: number;
}

/**
 * Auth + onboarding calls, named so every call site reads the same as the
 * route it hits rather than repeating a raw path string. Each comment notes
 * the exact backend route this reaches — see docs/FRONTEND-REDESIGN-PLAN.md
 * §16.1 for how each was confirmed to already exist.
 */
export const authApi = {
  register: (email: string, password: string) => api.post("/users", { email, password }),
  login: (email: string, password: string) => api.post("/auth/login", { email, password }),
  // POST /auth/forgot-password (gateway/server.go:138) -- the "send me a
  // link" step. Previously nothing in the frontend called this; ResetPasswordForm
  // called /auth/reset-password instead, which is actually the confirm step below.
  forgotPassword: (email: string) => api.post("/auth/forgot-password", { email }),
  // POST /auth/reset-password (gateway/server.go:139) -- confirms a reset with
  // the token from the emailed link plus a new password.
  resetPassword: (token: string, newPassword: string) =>
    api.post("/auth/reset-password", { token, newPassword }),
  // GET /auth/verify-email/:token (gateway/server.go:140).
  verifyEmail: (token: string) => api.get(`/auth/verify-email/${encodeURIComponent(token)}`),
  // PUT /api/profile (gateway/server.go, ProfileHandler.UpdateProfile) --
  // proxies to the User service's existing PUT /users/:id/profile. Added in
  // Phase 3 specifically so the onboarding wizard can persist its data instead
  // of discarding it.
  updateProfile: (payload: UpdateProfilePayload) => api.put("/api/profile", payload),
  // POST /api/writing/cv/upload (gateway/server.go:177) -- a paid-tier route
  // (subscriptionMiddleware.RequirePaid). Reused as-is for the onboarding CV
  // step; free-tier accounts get a 403 { error: "subscription_required" },
  // which the CV step surfaces as a specific upgrade prompt rather than a
  // generic failure.
  uploadCv: (
    file: File,
    options?: { onProgress?: (percent: number) => void; signal?: AbortSignal },
  ) => {
    const form = new FormData();
    form.append("file", file);
    return api.post("/api/writing/cv/upload", form, {
      signal: options?.signal,
      onUploadProgress: (event) => {
        if (options?.onProgress && event.total) {
          options.onProgress(Math.round((event.loaded / event.total) * 100));
        }
      },
    });
  },
  // POST /auth/logout (gateway/server.go:143) -- blacklists the access token
  // and clears the auth cookies server-side. Already existed; the app shell
  // previously had no user menu at all, so nothing called it.
  logout: () => api.post("/auth/logout"),
};
