import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { Combobox, Field, MultiCombobox, filterOptions } from "@/components/ui";
import type { ComboboxOption } from "@/components/ui";

const OPTIONS: ComboboxOption[] = [
  { value: "Germany", label: "Germany" },
  { value: "Netherlands", label: "Netherlands" },
  { value: "New Zealand", label: "New Zealand" },
  { value: "Sweden", label: "Sweden" },
  { value: "United Kingdom", label: "United Kingdom" },
];

describe("filterOptions", () => {
  it("ranks a prefix match above a mid-string one", () => {
    // Source order alone would put Netherlands first for "new"; a user typing
    // "new" means New Zealand.
    const results = filterOptions(OPTIONS, "new");
    expect(results[0].value).toBe("New Zealand");
  });

  it("is case- and accent-insensitive", () => {
    expect(filterOptions(OPTIONS, "GERMANY")).toHaveLength(1);
    expect(
      filterOptions([{ value: "Zürich", label: "Zürich" }], "zurich"),
    ).toHaveLength(1);
  });

  it("returns everything for an empty query", () => {
    expect(filterOptions(OPTIONS, "")).toHaveLength(OPTIONS.length);
  });

  it("returns nothing when there is no match", () => {
    expect(filterOptions(OPTIONS, "zzzz")).toEqual([]);
  });
});

function ControlledCombobox({
  allowCustomValue = false,
  onCommit,
}: {
  allowCustomValue?: boolean;
  onCommit?: (v: string) => void;
}) {
  const [value, setValue] = useState("");
  return (
    <Field label="Destination countries">
      <Combobox
        options={OPTIONS}
        value={value}
        onChange={(next) => {
          setValue(next);
          onCommit?.(next);
        }}
        allowCustomValue={allowCustomValue}
      />
    </Field>
  );
}

describe("Combobox", () => {
  it("takes its accessible name from the surrounding Field", () => {
    // The Field owns the control id; a Combobox that passed its own would
    // leave the <label for> dangling and the field unnamed.
    render(<ControlledCombobox />);
    expect(screen.getByLabelText("Destination countries")).toHaveAttribute(
      "role",
      "combobox",
    );
  });

  it("filters as you type and commits the option you click", async () => {
    const onCommit = vi.fn();
    const user = userEvent.setup();
    render(<ControlledCombobox onCommit={onCommit} />);

    const input = screen.getByLabelText("Destination countries");
    await user.click(input);
    await user.type(input, "neth");

    const options = screen.getAllByRole("option");
    expect(options).toHaveLength(1);

    await user.click(options[0]);
    expect(onCommit).toHaveBeenCalledWith("Netherlands");
    expect(input).toHaveValue("Netherlands");
  });

  it("commits the highlighted option on Enter", async () => {
    const onCommit = vi.fn();
    const user = userEvent.setup();
    render(<ControlledCombobox onCommit={onCommit} />);

    const input = screen.getByLabelText("Destination countries");
    await user.click(input);
    await user.type(input, "swe{Enter}");

    expect(onCommit).toHaveBeenCalledWith("Sweden");
  });

  it("refuses an off-list value when custom values are not allowed", async () => {
    const onCommit = vi.fn();
    const user = userEvent.setup();
    render(<ControlledCombobox onCommit={onCommit} />);

    const input = screen.getByLabelText("Destination countries");
    await user.click(input);
    await user.type(input, "Atlantis{Enter}");

    // Country has to match a value RAG can filter on, so an invented one is
    // discarded rather than silently persisted.
    expect(onCommit).not.toHaveBeenCalled();
  });

  it("accepts an off-list value when custom values are allowed", async () => {
    const onCommit = vi.fn();
    const user = userEvent.setup();
    render(<ControlledCombobox allowCustomValue onCommit={onCommit} />);

    const input = screen.getByLabelText("Destination countries");
    await user.click(input);
    await user.type(input, "Underwater Basket Weaving{Enter}");

    expect(onCommit).toHaveBeenCalledWith("Underwater Basket Weaving");
  });

  it("marks itself expanded and tracks the active option for screen readers", async () => {
    const user = userEvent.setup();
    render(<ControlledCombobox />);

    const input = screen.getByLabelText("Destination countries");
    expect(input).toHaveAttribute("aria-expanded", "false");

    await user.click(input);
    expect(input).toHaveAttribute("aria-expanded", "true");
    // The input keeps DOM focus; the highlight is conveyed by
    // aria-activedescendant, which is what keeps typing working.
    expect(input).toHaveAttribute("aria-activedescendant");
  });
});

function ControlledMulti() {
  const [values, setValues] = useState<string[]>([]);
  return (
    <Field label="Target countries">
      <MultiCombobox options={OPTIONS} values={values} onChange={setValues} max={2} />
    </Field>
  );
}

describe("MultiCombobox", () => {
  it("accumulates selections as removable chips and enforces the cap", async () => {
    const user = userEvent.setup();
    render(<ControlledMulti />);

    const input = screen.getByLabelText("Target countries");
    await user.click(input);
    await user.type(input, "germ{Enter}");
    expect(screen.getByRole("button", { name: "Remove Germany" })).toBeInTheDocument();

    await user.click(screen.getByLabelText("Target countries"));
    await user.type(screen.getByLabelText("Target countries"), "swe{Enter}");
    expect(screen.getByRole("button", { name: "Remove Sweden" })).toBeInTheDocument();

    // At the cap the search box is replaced by an explanation rather than
    // silently ignoring the next click.
    expect(screen.queryByLabelText("Target countries")).toBeNull();
    expect(screen.getByText(/maximum of 2/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Remove Germany" }));
    expect(screen.getByLabelText("Target countries")).toBeInTheDocument();
  });
});
