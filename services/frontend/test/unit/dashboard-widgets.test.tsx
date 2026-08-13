import { describe, expect, it, vi, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

const profileMock = vi.hoisted(() => ({ getMyProfile: vi.fn() }));
vi.mock("@/lib/profile-api", () => profileMock);

const examMock = vi.hoisted(() => ({ getExamProgress: vi.fn() }));
vi.mock("@/lib/exam-api", () => examMock);

const { WelcomeWidget } = await import("@/components/dashboard/welcome-widget");
const { ProgressWidget } = await import("@/components/dashboard/progress-widget");
const { RecommendationsWidget } = await import(
  "@/components/dashboard/recommendations-widget"
);

const BASE_PROFILE = {
  id: "user-1",
  subscriptionTier: "free" as const,
  isVerified: true,
  profile: null,
};

afterEach(() => {
  vi.clearAllMocks();
});

describe("WelcomeWidget", () => {
  it("turns a dotted email local part into a capitalised name", async () => {
    profileMock.getMyProfile.mockResolvedValue({
      ...BASE_PROFILE,
      email: "amina.hassan@example.com",
    });

    render(<WelcomeWidget />);

    await waitFor(() =>
      expect(screen.getByText(/Welcome back, Amina Hassan/)).toBeInTheDocument(),
    );
  });

  it("falls back to the raw email when the local part has no letters to capitalise", async () => {
    profileMock.getMyProfile.mockResolvedValue({
      ...BASE_PROFILE,
      email: "12345@example.com",
    });

    render(<WelcomeWidget />);

    await waitFor(() =>
      expect(
        screen.getByText(/Welcome back, 12345@example\.com/),
      ).toBeInTheDocument(),
    );
  });

  it("offers to complete the profile only when it's actually incomplete", async () => {
    profileMock.getMyProfile.mockResolvedValue({
      ...BASE_PROFILE,
      email: "student@example.com",
      profile: null,
    });

    render(<WelcomeWidget />);

    await waitFor(() =>
      expect(screen.getByRole("link", { name: "Complete your profile" })).toBeInTheDocument(),
    );
  });
});

describe("ProgressWidget", () => {
  it("counts only the fields onboarding actually collects", async () => {
    profileMock.getMyProfile.mockResolvedValue({
      ...BASE_PROFILE,
      email: "student@example.com",
      profile: {
        userId: "user-1",
        degreeLevel: "Bachelors",
        gpa: null,
        ieltsScore: null,
        ieltsListening: null,
        ieltsReading: null,
        ieltsWriting: null,
        ieltsSpeaking: null,
        targetCountries: [],
        fieldOfStudy: "Computer Science",
        ects: null,
        workExperienceYears: 0,
        extracurricularsScore: 0,
        gpaScale: "4.0",
      },
    });

    render(<ProgressWidget />);

    await waitFor(() => expect(screen.getByText("2 of 5 fields")).toBeInTheDocument());
  });
});

describe("RecommendationsWidget", () => {
  it("renders nothing when there is no exam data to derive a recommendation from", async () => {
    examMock.getExamProgress.mockResolvedValue({});

    const { container } = render(<RecommendationsWidget />);

    await waitFor(() => expect(examMock.getExamProgress).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });

  it("recommends the skill with the lowest most-recent band", async () => {
    examMock.getExamProgress.mockResolvedValue({
      writing: [{ date: "2026-01-01", band: 7.5 }],
      speaking: [
        { date: "2026-01-01", band: 6.0 },
        { date: "2026-02-01", band: 5.5 },
      ],
    });

    render(<RecommendationsWidget />);

    await waitFor(() =>
      expect(screen.getByText(/Speaking is your lowest-scored skill/)).toBeInTheDocument(),
    );
    // Must pick the *latest* speaking attempt (5.5), not the first one (6.0).
    expect(screen.getByText(/band 5\.5/)).toBeInTheDocument();
  });
});
