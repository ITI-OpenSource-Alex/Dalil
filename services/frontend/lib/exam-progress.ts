import { type ExamProgress } from "@/lib/exam-api";
import { roundToBand } from "@/lib/ielts";

const SKILLS = ["reading", "listening", "speaking", "writing"] as const;

export function estimateOverallPracticeBand(
  progress: ExamProgress,
): number | null {
  const latest: number[] = [];
  for (const skill of SKILLS) {
    const points = progress[skill];
    if (!points || points.length === 0) continue;
    latest.push(points[points.length - 1].band);
  }
  if (latest.length === 0) return null;
  const mean = latest.reduce((a, b) => a + b, 0) / latest.length;
  return roundToBand(mean);
}

export function isExamProgressEmpty(
  progress: ExamProgress,
  historyLength: number,
): boolean {
  if (historyLength > 0) return false;
  return SKILLS.every((skill) => !progress[skill]?.length);
}
