export interface ProgrammePromptContext {
  programName: string;
  university: string;
  country?: string | null;
}

/**
 * Contextual entry points paste normal, editable user text into Dalil. They do
 * not select a special chat mode or send hidden metadata: after this turn the
 * conversation remains the same general-purpose chat it always was.
 */
export function programmeAdvicePrompt({
  programName,
  university,
  country,
}: ProgrammePromptContext): string {
  const location = country ? ` in ${country}` : "";
  return (
    `Tell me more about ${programName} at ${university}${location}. ` +
    "Explain how it fits my profile, the important admission requirements, " +
    "and the gaps I should address before applying."
  );
}

export function noMatchesAdvicePrompt(): string {
  return (
    "No programmes matched my current profile and targets. Help me understand " +
    "which countries, degree preferences, or profile gaps I should reconsider, " +
    "and explain the trade-offs."
  );
}
