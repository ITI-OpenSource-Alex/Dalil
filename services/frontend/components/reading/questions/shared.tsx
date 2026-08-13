"use client";

interface QuestionShellProps {
  number: number;
  prompt: string;
  instructions?: string | null;
  children: React.ReactNode;
}

/** Common number/prompt/instructions header every question type renders
 * before its own answer control. */
export function QuestionShell({
  number,
  prompt,
  instructions,
  children,
}: QuestionShellProps) {
  return (
    <div data-testid={`question-${number}`} className="space-y-2">
      <p className="text-sm text-fg-muted">
        <span className="mr-2 font-semibold text-fg">{number}.</span>
        {prompt}
      </p>
      {instructions && (
        <p className="text-xs italic text-fg-subtle">{instructions}</p>
      )}
      {children}
    </div>
  );
}

interface TextAnswerInputProps {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
}

/** Shared plain-text answer control used by both FillInBlankQuestion and
 * ShortAnswerQuestion — the two currently only differ in surrounding
 * copy/labeling, not in how the answer itself is captured. */
export function TextAnswerInput({
  value,
  onChange,
  placeholder,
}: TextAnswerInputProps) {
  return (
    <input
      type="text"
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder ?? "Type your answer"}
      className="w-full max-w-sm rounded-lg border border-border-strong px-3 py-1.5 text-sm outline-none focus:border-brand focus:ring-2 focus:ring-brand-muted"
    />
  );
}
