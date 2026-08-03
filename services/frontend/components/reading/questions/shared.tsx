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
      <p className="text-sm text-gray-800">
        <span className="mr-2 font-semibold text-gray-900">{number}.</span>
        {prompt}
      </p>
      {instructions && (
        <p className="text-xs italic text-gray-500">{instructions}</p>
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
      className="w-full max-w-sm rounded-lg border border-gray-300 px-3 py-1.5 text-sm outline-none focus:border-emerald-600 focus:ring-2 focus:ring-emerald-600/20"
    />
  );
}
