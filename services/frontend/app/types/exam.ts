export type ExamType = "Academic" | "General";
export type SkillArea = "Reading" | "Listening" | "Speaking" | "Writing";

export interface ExamSession {
  sessionId: string;
  examType: ExamType;
  skillArea: SkillArea;
  totalSecondsRemaining: number;
}

// State Machine Statuses
export type SpeakingStatus =
  | "in_progress"
  | "part1_done"
  | "part2_done"
  | "part3_done"
  | "evaluating"
  | "results";
export type WritingStatus =
  | "task1_submitted"
  | "task1_evaluating"
  | "task1_done"
  | "task2_writing"
  | "task2_submitted"
  | "task2_evaluating"
  | "combined_results";
export type StandardStatus = "submitted" | "results";

export type ExamStatus = SpeakingStatus | WritingStatus | StandardStatus;
