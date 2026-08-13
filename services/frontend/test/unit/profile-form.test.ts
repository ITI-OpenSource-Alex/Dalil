import { describe, expect, it } from "vitest";
import {
  payloadFromValues,
  validateProfile,
  type ProfileFormValues,
} from "@/components/profile/profile-form";

const base: ProfileFormValues = {
  degreeLevel: "Bachelors",
  fieldOfStudy: "Computer Science",
  targetFieldOfStudy: "Software Engineering",
  gpa: "3.8",
  gpaScale: "4.0",
  ects: "180",
  ieltsListening: "7.5",
  ieltsReading: "7.0",
  ieltsWriting: "6.5",
  ieltsSpeaking: "7.0",
  ieltsScore: "7.0",
  overrideOverall: false,
  workExperienceYears: "2",
  extracurricularsScore: "6",
  targetCountries: ["Germany"],
};

describe("payloadFromValues", () => {
  it("includes gpaScale with gpa and Stage-2 fields", () => {
    const p = payloadFromValues(base);
    expect(p.gpa).toBe(3.8);
    expect(p.gpaScale).toBe("4.0");
    expect(p.targetFieldOfStudy).toBe("Software Engineering");
    expect(p.workExperienceYears).toBe(2);
    expect(p.extracurricularsScore).toBe(6);
    expect(p.ieltsListening).toBe(7.5);
    expect(p.ieltsScore).toBe(7.0);
  });
});

describe("validateProfile", () => {
  it("rejects GPA above selected scale", () => {
    const errors = validateProfile({ ...base, gpa: "4.5", gpaScale: "4.0" });
    expect(errors.gpa).toBeTruthy();
  });
});
