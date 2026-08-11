import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { ProfileForm } from "@/components/profile/profile-form";
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

describe("ProfileForm sections", () => {
  it("groups the fields under named section headings", () => {
    render(<ProfileForm profile={PROFILE} />);
    expect(
      screen.getByRole("heading", { name: "Academic background" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "English (IELTS)" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Experience" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Study preferences" }),
    ).toBeInTheDocument();
  });

  it("exposes the anchors the completeness card deep-links to", () => {
    const { container } = render(<ProfileForm profile={PROFILE} />);
    expect(container.querySelector("#profile-section-academic")).not.toBeNull();
    expect(container.querySelector("#profile-section-ielts")).not.toBeNull();
    expect(
      container.querySelector("#profile-section-destinations"),
    ).not.toBeNull();
  });

  it("keeps the field labels the existing tests select on", () => {
    render(<ProfileForm profile={PROFILE} />);
    expect(screen.getByLabelText("GPA")).toBeInTheDocument();
    expect(screen.getByLabelText("ECTS credits")).toBeInTheDocument();
  });
});
