"use client";

import { Minus, Plus } from "lucide-react";
import { cn } from "@/lib/cn";
import { BAND_VALUES, formatBand, isValidBand, parseBand } from "@/lib/ielts";
import { Icon } from "@/components/ui";

/* ------------------------------------------------------------------ *
 * A band score is not a free number, and typing it into `<input
 * type="number" step={0.5}>` treated it like one: nothing stopped 8.3 or
 * 12, the browser's spinner arrows are a 12px target, and on mobile the
 * decimal keypad is the wrong tool for a value with 19 legal states.
 *
 * This control makes the 19 legal values the *only* reachable ones. The
 * primary interaction is the segmented rail (tap the band you got); the
 * -/+ buttons give a keyboard- and thumb-friendly way to nudge; and the
 * whole thing is a real ARIA slider, so it is operable with arrow keys
 * and announces "7.5 out of 9" rather than reading out an empty textbox.
 * ------------------------------------------------------------------ */

interface BandScoreInputProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  error?: string;
  id?: string;
  /** Suppresses the descriptive caption in dense four-across layouts. */
  compact?: boolean;
}

export function BandScoreInput({
  label,
  value,
  onChange,
  error,
  id,
  compact = false,
}: BandScoreInputProps) {
  const current = parseBand(value);
  const index = current === null ? -1 : BAND_VALUES.indexOf(current);

  function step(direction: 1 | -1) {
    // From empty, the first nudge lands on 6.0 rather than 0.0 or 9.0:
    // starting a candidate at "extremely limited user" is a poor default and
    // 0.0 is not a band anyone is reporting.
    const nextIndex =
      index === -1
        ? BAND_VALUES.indexOf(6)
        : Math.min(BAND_VALUES.length - 1, Math.max(0, index + direction));
    onChange(formatBand(BAND_VALUES[nextIndex]));
  }

  function handleKeyDown(event: React.KeyboardEvent<HTMLDivElement>) {
    switch (event.key) {
      case "ArrowRight":
      case "ArrowUp":
        event.preventDefault();
        step(1);
        break;
      case "ArrowLeft":
      case "ArrowDown":
        event.preventDefault();
        step(-1);
        break;
      case "Home":
        event.preventDefault();
        onChange(formatBand(4));
        break;
      case "End":
        event.preventDefault();
        onChange(formatBand(9));
        break;
    }
  }

  // Bands below 4.0 are vanishingly rare among applicants and would double the
  // width of the rail. They stay reachable through Home and the - button.
  const railValues = BAND_VALUES.filter((v) => v >= 4);

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-baseline justify-between gap-2">
        <span id={`${id}-label`} className="text-sm font-medium text-fg">
          {label}
        </span>
        <span
          className={cn(
            "text-sm font-bold tabular-nums",
            current === null ? "text-fg-subtle" : "text-brand-fg",
          )}
        >
          {current === null ? "—" : formatBand(current)}
        </span>
      </div>

      <div className="flex items-center gap-2">
        <button
          type="button"
          aria-label={`Decrease ${label} band`}
          onClick={() => step(-1)}
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-control border border-border bg-surface text-fg-muted transition-colors hover:bg-canvas-subtle hover:text-fg"
        >
          <Icon icon={Minus} size="xs" />
        </button>

        <div
          role="slider"
          tabIndex={0}
          aria-labelledby={`${id}-label`}
          aria-valuemin={0}
          aria-valuemax={9}
          aria-valuenow={current ?? undefined}
          aria-valuetext={
            current === null ? "Not set" : `Band ${formatBand(current)} of 9`
          }
          aria-invalid={error ? true : undefined}
          onKeyDown={handleKeyDown}
          className={cn(
            "flex min-w-0 flex-1 gap-0.5 rounded-control border p-1 transition-colors",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-muted",
            error
              ? "border-danger-border bg-danger-subtle"
              : "border-border bg-canvas-subtle",
          )}
        >
          {railValues.map((band) => {
            const selected = current === band;
            const isWhole = Number.isInteger(band);
            return (
              <button
                key={band}
                type="button"
                // The rail is one slider to assistive tech, so its segments
                // must not each announce as a separate control.
                aria-hidden="true"
                tabIndex={-1}
                onClick={() => onChange(formatBand(band))}
                title={`Band ${formatBand(band)}`}
                className={cn(
                  "min-w-0 flex-1 rounded-chip py-1.5 text-[11px] font-semibold transition-colors",
                  selected
                    ? "bg-brand text-fg-on-brand"
                    : isWhole
                      ? "text-fg-muted hover:bg-brand-subtle hover:text-brand-fg"
                      : "text-fg-subtle hover:bg-brand-subtle hover:text-brand-fg",
                )}
              >
                {/* Half bands show only the decimal, so eleven labels fit a
                    320px viewport without truncating the whole numbers. */}
                {isWhole ? band : `${formatBand(band).slice(-2)}`}
              </button>
            );
          })}
        </div>

        <button
          type="button"
          aria-label={`Increase ${label} band`}
          onClick={() => step(1)}
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-control border border-border bg-surface text-fg-muted transition-colors hover:bg-canvas-subtle hover:text-fg"
        >
          <Icon icon={Plus} size="xs" />
        </button>
      </div>

      {!compact && !error && (
        <p className="text-xs text-fg-subtle">
          Tap a band, or use the arrow keys.
        </p>
      )}

      {error && (
        <p role="alert" className="text-sm text-danger-fg">
          {error}
        </p>
      )}
    </div>
  );
}

/**
 * Guards the free-text fallback used for the manually-overridden overall band
 * and the target score, where a rail would be the wrong affordance (a target
 * is aspirational, not a value being reported).
 */
export function bandError(value: string, required: boolean): string | undefined {
  if (!value.trim()) {
    return required ? "Required" : undefined;
  }
  const num = Number(value);
  if (Number.isNaN(num)) return "Enter a number between 0 and 9.";
  if (num < 0 || num > 9) return "Bands run from 0 to 9.";
  if (!isValidBand(num)) return "Bands go in half steps — 6.5, not 6.4.";
  return undefined;
}
