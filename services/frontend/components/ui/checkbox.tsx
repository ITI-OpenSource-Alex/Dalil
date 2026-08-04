"use client";

export default function Checkbox({
  checked,
  onChange,
  disabled = false,
  label,
}: {
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
  label: string;
}) {
  return (
    <button
      type="button"
      role="checkbox"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={() => !disabled && onChange(!checked)}
      className={`shrink-0 h-5 w-5 rounded-md border flex items-center justify-center transition ${
        disabled
          ? "border-gray-200 bg-gray-100 cursor-not-allowed"
          : checked
            ? "border-emerald-600 bg-emerald-600"
            : "border-gray-300 bg-white hover:border-emerald-400"
      }`}
    >
      {checked && (
        <svg
          viewBox="0 0 16 16"
          fill="none"
          className="h-3.5 w-3.5 text-white"
          aria-hidden="true"
        >
          <path
            d="M3.5 8.5L6.5 11.5L12.5 4.5"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      )}
    </button>
  );
}
