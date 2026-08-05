"use client";

import React, { useEffect, useId, useMemo, useRef, useState } from "react";
import { Check, ChevronDown, Search, X } from "lucide-react";
import { cn } from "@/lib/cn";
import { Icon } from "./icon";
import { useFieldControl } from "./field";
import { CONTROL_BASE, CONTROL_INVALID, CONTROL_VALID } from "./input";

/* ------------------------------------------------------------------ *
 * A searchable select, built on the same CONTROL_BASE skin as Input and
 * Select so it is visually indistinguishable from the rest of the form.
 *
 * input.tsx argues — correctly — that a native <select> beats a custom
 * listbox for a short list of options. That argument stops holding at
 * ~28 countries and ~45 fields of study, where the native control offers
 * no filtering and the user is left scrolling. This component exists for
 * exactly those lists; short enumerations should keep using <Select>.
 *
 * It implements the combobox pattern properly rather than approximately:
 * aria-expanded/aria-controls on the input, aria-activedescendant tracking
 * the highlighted row (so the input keeps DOM focus and typing keeps
 * working), roving highlight on Arrow keys, Enter to commit, Escape to
 * cancel back to the committed value, and a click-outside that commits
 * rather than silently discarding what was typed.
 * ------------------------------------------------------------------ */

export interface ComboboxOption {
  value: string;
  label: string;
  /** Secondary line, e.g. "In our catalogue". */
  description?: string;
  /** Decorative prefix, e.g. a flag glyph. Always rendered aria-hidden. */
  prefix?: string;
}

function normalise(text: string): string {
  return text
    .toLowerCase()
    .normalize("NFD")
    // Strip combining marks so "Zurich" finds "Zürich".
    .replace(/[̀-ͯ]/g, "");
}

/**
 * Ranks matches so a prefix hit outranks a mid-word hit: typing "ne" should
 * offer Netherlands before "Chennai", which a plain `includes` filter does not
 * do because it preserves source order.
 */
export function filterOptions(
  options: ComboboxOption[],
  query: string,
  limit = 50,
): ComboboxOption[] {
  const q = normalise(query.trim());
  if (!q) return options.slice(0, limit);

  const scored: { option: ComboboxOption; rank: number }[] = [];
  for (const option of options) {
    const label = normalise(option.label);
    if (label.startsWith(q)) scored.push({ option, rank: 0 });
    else if (label.includes(` ${q}`)) scored.push({ option, rank: 1 });
    else if (label.includes(q)) scored.push({ option, rank: 2 });
  }
  scored.sort((a, b) => a.rank - b.rank);
  return scored.slice(0, limit).map((s) => s.option);
}

export interface ComboboxProps {
  options: ComboboxOption[];
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  /**
   * Allows committing a value that is not in `options`. On for fields where
   * the list is a convenience (field of study, university) and off where the
   * value has to match a backend enumeration (country).
   */
  allowCustomValue?: boolean;
  invalid?: boolean;
  disabled?: boolean;
  id?: string;
  name?: string;
  emptyMessage?: string;
  className?: string;
}

export function Combobox({
  options,
  value,
  onChange,
  placeholder = "Search…",
  allowCustomValue = false,
  invalid: invalidProp,
  disabled: disabledProp,
  id,
  name,
  emptyMessage = "No matches. Try a different search.",
  className,
}: ComboboxProps) {
  const field = useFieldControl({
    id,
    invalid: invalidProp,
    disabled: disabledProp,
  });
  const { invalid, disabled, ...aria } = field;

  const listId = useId();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [highlight, setHighlight] = useState(0);
  const containerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLUListElement>(null);

  const selected = useMemo(
    () => options.find((o) => o.value === value) ?? null,
    [options, value],
  );

  // What the text box shows: the query while the user is actively searching,
  // otherwise the committed selection's label (or the raw value, for a custom
  // one that has no matching option).
  const displayValue = open ? query : (selected?.label ?? value);

  const results = useMemo(
    () => filterOptions(options, open ? query : ""),
    [options, open, query],
  );

  // Clamp rather than reset to 0 on every keystroke: the highlight should stay
  // put when the list merely shrinks around it.
  useEffect(() => {
    setHighlight((h) => (h >= results.length ? 0 : h));
  }, [results.length]);

  useEffect(() => {
    if (!open) return;
    listRef.current
      ?.querySelector<HTMLElement>('[data-highlighted="true"]')
      ?.scrollIntoView({ block: "nearest" });
  }, [highlight, open]);

  function commit(next: string) {
    onChange(next);
    setQuery("");
    setOpen(false);
  }

  function openList() {
    if (disabled) return;
    setQuery("");
    setHighlight(Math.max(0, options.findIndex((o) => o.value === value)));
    setOpen(true);
  }

  /**
   * Leaving the field commits what was typed when custom values are allowed,
   * and reverts otherwise. Discarding a typed-but-uncommitted value on blur is
   * the single most common way a combobox loses a user's input.
   */
  function closeAndSettle() {
    if (!open) return;
    const typed = query.trim();
    if (typed) {
      const exact = options.find(
        (o) => normalise(o.label) === normalise(typed),
      );
      if (exact) {
        commit(exact.value);
        return;
      }
      if (allowCustomValue) {
        commit(typed);
        return;
      }
    }
    setQuery("");
    setOpen(false);
  }

  useEffect(() => {
    if (!open) return;

    function handlePointerDown(event: PointerEvent) {
      if (!containerRef.current?.contains(event.target as Node)) {
        closeAndSettle();
      }
    }
    document.addEventListener("pointerdown", handlePointerDown);
    return () => document.removeEventListener("pointerdown", handlePointerDown);
  });

  function handleKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    switch (event.key) {
      case "ArrowDown":
        event.preventDefault();
        if (!open) {
          openList();
          return;
        }
        setHighlight((h) => (results.length ? (h + 1) % results.length : 0));
        break;
      case "ArrowUp":
        event.preventDefault();
        if (!open) {
          openList();
          return;
        }
        setHighlight((h) =>
          results.length ? (h - 1 + results.length) % results.length : 0,
        );
        break;
      case "Enter": {
        if (!open) return;
        // Only swallow the Enter when it actually does something here —
        // otherwise a closed combobox would block the surrounding form's
        // submit-on-Enter.
        event.preventDefault();
        const option = results[highlight];
        if (option) commit(option.value);
        else closeAndSettle();
        break;
      }
      case "Escape":
        if (!open) return;
        event.preventDefault();
        // Cancel, explicitly: back to the committed value, not to what was typed.
        setQuery("");
        setOpen(false);
        break;
      case "Tab":
        closeAndSettle();
        break;
    }
  }

  return (
    <div ref={containerRef} className={cn("relative", className)}>
      <div className="relative">
        <span className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3.5 text-fg-subtle">
          <Icon icon={Search} size="sm" />
        </span>

        <input
          {...aria}
          ref={inputRef}
          name={name}
          type="text"
          role="combobox"
          autoComplete="off"
          // Safari/iOS otherwise offer autocorrect on a field whose whole job
          // is matching an exact catalogue value.
          autoCorrect="off"
          autoCapitalize="off"
          spellCheck={false}
          disabled={disabled}
          aria-expanded={open}
          aria-controls={open ? listId : undefined}
          aria-autocomplete="list"
          aria-activedescendant={
            open && results[highlight] ? `${listId}-${highlight}` : undefined
          }
          value={displayValue}
          placeholder={placeholder}
          onChange={(e) => {
            if (!open) setOpen(true);
            setQuery(e.target.value);
            setHighlight(0);
          }}
          onFocus={() => {
            if (!open) openList();
          }}
          onKeyDown={handleKeyDown}
          className={cn(
            CONTROL_BASE,
            invalid ? CONTROL_INVALID : CONTROL_VALID,
            "h-11 pr-10 pl-10 text-sm",
          )}
        />

        {value && !disabled ? (
          <button
            type="button"
            aria-label="Clear selection"
            onClick={() => {
              commit("");
              inputRef.current?.focus();
            }}
            className="absolute inset-y-0 right-0 flex items-center pr-3 text-fg-subtle transition-colors hover:text-fg"
          >
            <Icon icon={X} size="sm" />
          </button>
        ) : (
          <span className="pointer-events-none absolute inset-y-0 right-0 flex items-center pr-3.5 text-fg-subtle">
            <Icon icon={ChevronDown} size="sm" />
          </span>
        )}
      </div>

      {open && (
        <ul
          ref={listRef}
          id={listId}
          role="listbox"
          className="absolute z-50 mt-1 max-h-64 w-full overflow-y-auto rounded-panel border border-border bg-surface-raised p-1 shadow-e2"
        >
          {results.length === 0 && (
            <li className="px-3 py-2.5 text-sm text-fg-subtle">
              {allowCustomValue && query.trim()
                ? `Press Enter to use “${query.trim()}”`
                : emptyMessage}
            </li>
          )}

          {results.map((option, index) => {
            const isSelected = option.value === value;
            const isHighlighted = index === highlight;
            return (
              <li
                key={option.value}
                id={`${listId}-${index}`}
                role="option"
                aria-selected={isSelected}
                data-highlighted={isHighlighted}
                // onPointerDown, not onClick: the document-level pointerdown
                // listener above would otherwise close the list before the
                // click ever lands.
                onPointerDown={(e) => {
                  e.preventDefault();
                  commit(option.value);
                }}
                onMouseEnter={() => setHighlight(index)}
                className={cn(
                  "flex cursor-pointer items-center gap-2.5 rounded-control px-3 py-2 text-sm transition-colors",
                  isHighlighted ? "bg-canvas-subtle text-fg" : "text-fg-muted",
                )}
              >
                {option.prefix && (
                  <span aria-hidden="true" className="shrink-0 text-base">
                    {option.prefix}
                  </span>
                )}
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-medium text-fg">
                    {option.label}
                  </span>
                  {option.description && (
                    <span className="block truncate text-xs text-fg-subtle">
                      {option.description}
                    </span>
                  )}
                </span>
                {isSelected && (
                  <Icon icon={Check} size="xs" className="shrink-0 text-brand-fg" />
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

export interface MultiComboboxProps
  extends Omit<ComboboxProps, "value" | "onChange" | "allowCustomValue"> {
  values: string[];
  onChange: (values: string[]) => void;
  /** Soft cap, enforced with a message rather than a silently ignored click. */
  max?: number;
}

/**
 * The multi-select sibling. Selections render as removable chips above the
 * search box rather than inside it: a wrapping chip row inside a fixed-height
 * control is the usual source of multi-select layout breakage on narrow
 * viewports, and this keeps the control the same height as every other field.
 */
export function MultiCombobox({
  options,
  values,
  onChange,
  placeholder = "Search…",
  invalid,
  disabled,
  id,
  emptyMessage,
  max,
  className,
}: MultiComboboxProps) {
  const atLimit = max !== undefined && values.length >= max;

  const available = useMemo(
    () => options.filter((o) => !values.includes(o.value)),
    [options, values],
  );

  const selectedOptions = values.map(
    (v) => options.find((o) => o.value === v) ?? { value: v, label: v },
  );

  return (
    <div className={cn("flex flex-col gap-2", className)}>
      {selectedOptions.length > 0 && (
        <ul className="flex flex-wrap gap-2">
          {selectedOptions.map((option) => (
            <li key={option.value}>
              <span className="inline-flex items-center gap-1.5 rounded-chip border border-brand-border bg-brand-subtle py-1 pr-1.5 pl-2.5 text-sm font-medium text-brand-fg">
                {option.prefix && (
                  <span aria-hidden="true">{option.prefix}</span>
                )}
                {option.label}
                <button
                  type="button"
                  aria-label={`Remove ${option.label}`}
                  disabled={disabled}
                  onClick={() =>
                    onChange(values.filter((v) => v !== option.value))
                  }
                  className="rounded-full p-0.5 text-brand-fg/70 transition-colors hover:bg-brand-muted hover:text-brand-fg"
                >
                  <Icon icon={X} size="xs" />
                </button>
              </span>
            </li>
          ))}
        </ul>
      )}

      {atLimit ? (
        <p className="text-sm text-fg-subtle">
          That&apos;s the maximum of {max}. Remove one to add another.
        </p>
      ) : (
        <Combobox
          id={id}
          options={available}
          value=""
          onChange={(next) => {
            if (next) onChange([...values, next]);
          }}
          placeholder={placeholder}
          invalid={invalid}
          disabled={disabled}
          emptyMessage={emptyMessage}
        />
      )}
    </div>
  );
}
