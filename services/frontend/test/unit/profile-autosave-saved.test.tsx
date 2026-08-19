import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

const apiMock = vi.hoisted(() => ({
  authApi: { updateProfile: vi.fn() },
  apiErrorMessage: () => "Could not save your profile.",
}));
vi.mock("@/lib/api", () => apiMock);

const { ProfileForm } = await import("@/components/profile/profile-form");

import type { UserProfileDetail } from "@/app/types/profile";

const PROFILE: UserProfileDetail = {
  userId: "user-1",
  degreeLevel: "Bachelors",
  gpa: 3.2,
  gpaScale: "4.0",
  ects: 180,
  ieltsScore: 7,
  ieltsListening: 7,
  ieltsReading: 7,
  ieltsWriting: 7,
  ieltsSpeaking: 7,
  targetCountries: ["Germany"],
  fieldOfStudy: "Computer Science",
  targetFieldOfStudy: "Software Engineering",
  workExperienceYears: 1,
  extracurricularsScore: 5,
};

afterEach(() => {
  vi.clearAllMocks();
});

describe("ProfileForm onSaved", () => {
  it("announces a successful save so matches can be re-ranked", async () => {
    apiMock.authApi.updateProfile.mockResolvedValue({});
    const onSaved = vi.fn();

    render(<ProfileForm profile={PROFILE} onSaved={onSaved} />);

    const gpa = screen.getByLabelText("GPA");
    await userEvent.clear(gpa);
    await userEvent.type(gpa, "3.9");
    await userEvent.tab();

    await waitFor(() => expect(onSaved).toHaveBeenCalledTimes(1));
  });

  it("stays quiet when the save fails", async () => {
    apiMock.authApi.updateProfile.mockRejectedValue(new Error("boom"));
    const onSaved = vi.fn();

    render(<ProfileForm profile={PROFILE} onSaved={onSaved} />);

    const gpa = screen.getByLabelText("GPA");
    await userEvent.clear(gpa);
    await userEvent.type(gpa, "3.7");
    await userEvent.tab();

    await waitFor(() =>
      expect(apiMock.authApi.updateProfile).toHaveBeenCalled(),
    );
    expect(onSaved).not.toHaveBeenCalled();
  });

  it("stays quiet when nothing actually changed", async () => {
    apiMock.authApi.updateProfile.mockResolvedValue({});
    const onSaved = vi.fn();

    render(<ProfileForm profile={PROFILE} onSaved={onSaved} />);

    await userEvent.click(screen.getByLabelText("GPA"));
    await userEvent.tab();

    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(apiMock.authApi.updateProfile).not.toHaveBeenCalled();
    expect(onSaved).not.toHaveBeenCalled();
  });
});
