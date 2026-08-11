import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ProfileCompletenessCard } from "@/components/profile/profile-completeness-card";
import type { UserProfileDetail } from "@/app/types/profile";

const PARTIAL: UserProfileDetail = {
  userId: "user-1",
  degreeLevel: "Bachelors",
  gpa: 3.2,
  gpaScale: "4.0",
  ects: null,
  ieltsScore: null,
  ieltsListening: null,
  ieltsReading: null,
  ieltsWriting: null,
  ieltsSpeaking: null,
  targetCountries: [],
  fieldOfStudy: "Computer Science",
  targetFieldOfStudy: null,
  workExperienceYears: 0,
  extracurricularsScore: 0,
};

const READY: UserProfileDetail = {
  ...PARTIAL,
  ects: 180,
  ieltsScore: 7,
  targetCountries: ["Germany"],
};

describe("ProfileCompletenessCard", () => {
  it("reports how many matching details are present", () => {
    render(<ProfileCompletenessCard profile={PARTIAL} onFix={vi.fn()} />);
    const meter = screen.getByRole("progressbar");
    expect(meter).toHaveAttribute("aria-valuenow", "3");
    expect(meter).toHaveAttribute("aria-valuemax", "6");
    expect(screen.getByText("3 of 6 details")).toBeInTheDocument();
  });

  it("offers a jump button for each missing detail", async () => {
    const onFix = vi.fn();
    render(<ProfileCompletenessCard profile={PARTIAL} onFix={onFix} />);

    await userEvent.click(
      screen.getByRole("button", { name: "Add ECTS credits" }),
    );
    expect(onFix).toHaveBeenCalledWith("profile-section-academic");

    await userEvent.click(
      screen.getByRole("button", { name: "Add Target countries" }),
    );
    expect(onFix).toHaveBeenCalledWith("profile-section-destinations");
  });

  it("congratulates a complete profile instead of listing gaps", () => {
    render(<ProfileCompletenessCard profile={READY} onFix={vi.fn()} />);
    expect(screen.getByRole("progressbar")).toHaveAttribute(
      "aria-valuenow",
      "6",
    );
    expect(screen.queryByRole("button", { name: /^Add / })).toBeNull();
    expect(
      screen.getByText(/everything programme matching reads/i),
    ).toBeInTheDocument();
  });

  it("links to the guided wizard while details are missing", () => {
    render(<ProfileCompletenessCard profile={PARTIAL} onFix={vi.fn()} />);
    expect(
      screen.getByRole("link", { name: "Use the guided wizard" }),
    ).toHaveAttribute("href", "/onboarding");
  });
});
