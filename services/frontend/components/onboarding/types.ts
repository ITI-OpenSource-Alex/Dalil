export interface AcademicData {
  degree: string;
  major: string;
  university: string;
  gradYear: string;
  gpa: string;
  gpaScale: "4.0" | "100";
  ects: string;
}

export interface LanguageData {
  hasTakenIelts: "yes" | "no" | "";
  listeningScore: string;
  readingScore: string;
  writingScore: string;
  speakingScore: string;
  overallScore: string;
  planningToTake: "yes" | "no" | "";
  targetOverallScore: string;
  targetExamDate: string;
}

export interface TargetsData {
  destinations: string[];
  targetDegree: string;
  targetMajor: string;
  targetIntake: string;
}

export const EMPTY_ACADEMIC: AcademicData = {
  degree: "",
  major: "",
  university: "",
  gradYear: "",
  gpa: "",
  gpaScale: "4.0",
  ects: "",
};

export const EMPTY_LANGUAGE: LanguageData = {
  hasTakenIelts: "",
  listeningScore: "",
  readingScore: "",
  writingScore: "",
  speakingScore: "",
  overallScore: "",
  planningToTake: "",
  targetOverallScore: "",
  targetExamDate: "",
};

export const EMPTY_TARGETS: TargetsData = {
  destinations: [],
  targetDegree: "",
  targetMajor: "",
  targetIntake: "",
};

export const DESTINATION_COUNTRIES = [
  { id: "us", name: "United States" },
  { id: "uk", name: "United Kingdom" },
  { id: "ca", name: "Canada" },
  { id: "de", name: "Germany" },
  { id: "au", name: "Australia" },
  { id: "eu", name: "Other Europe" },
] as const;
