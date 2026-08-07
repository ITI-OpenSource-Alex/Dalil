import type { Phase } from "@/app/types/checklist";

// The checklist backend (GOA-084) tags each generated item with a free-text
// `category` (its own prompt asks the LLM for values like "documents", "language",
// "administrative") rather than one of GOA-035's five fixed phases — there is no
// phase field to read. This is a best-effort client-side grouping until GOA-084
// adds one.
//
// "Financial Requirements" is deliberately not a possible return value here: that
// phase must only ever be populated from the structured
// FinancialRequirementsResponse (GOA-108 visa data), never from an LLM-authored
// category string. A category that reads as financial ("financial", "funding",
// "fee") is routed to Application instead of being allowed anywhere near the
// trusted Financial Requirements section.
type GeneratedPhase = Exclude<Phase, "Financial Requirements">;

const KEYWORD_RULES: Array<{ phase: GeneratedPhase; keywords: string[] }> = [
  { phase: "Language Prep", keywords: ["language", "ielts", "toefl", "english"] },
  {
    phase: "Post-acceptance",
    keywords: ["accept", "enroll", "arrival", "orientation", "visa_appointment"],
  },
  {
    phase: "Documents",
    keywords: [
      "document",
      "transcript",
      "passport",
      "letter",
      "recommendation",
      "cv",
      "resume",
      "motivation",
      "certificate",
    ],
  },
];

export function phaseForItem(category: string | null, itemId: string): GeneratedPhase {
  const haystack = `${category ?? ""} ${itemId}`.toLowerCase();
  for (const rule of KEYWORD_RULES) {
    if (rule.keywords.some((keyword) => haystack.includes(keyword))) {
      return rule.phase;
    }
  }
  // Application fees, unrecognized categories, and anything financial-sounding
  // (e.g. "financial", "funding") land here rather than in Documents or, worse,
  // Financial Requirements — see module comment.
  return "Application";
}
