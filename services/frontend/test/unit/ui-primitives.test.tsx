import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input, Select, Textarea } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/checkbox";
import { Switch } from "@/components/ui/switch";
import { Progress } from "@/components/ui/progress";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Heading } from "@/components/ui/heading";
import { cn } from "@/lib/cn";

/* These assert BEHAVIOUR and ACCESSIBILITY, not markup. Class names are
   deliberately not asserted anywhere -- doing so would make the design system
   impossible to restyle, which is the whole point of building it. */

describe("cn", () => {
  it("lets a caller's class win over a component default", () => {
    expect(cn("bg-brand", "bg-danger")).toBe("bg-danger");
  });

  it("understands the semantic radius scale", () => {
    // Without extendTailwindMerge these would both survive and the winner
    // would depend on stylesheet order.
    expect(cn("rounded-control", "rounded-card")).toBe("rounded-card");
  });

  it("understands the elevation scale", () => {
    expect(cn("shadow-e1", "shadow-e3")).toBe("shadow-e3");
  });

  it("keeps unrelated utilities", () => {
    expect(cn("flex", "bg-brand", "p-4")).toBe("flex bg-brand p-4");
  });
});

describe("Button", () => {
  it("defaults to type=button so it cannot submit a form by accident", () => {
    render(<Button>Save</Button>);
    expect(screen.getByRole("button")).toHaveAttribute("type", "button");
  });

  it("honours an explicit type", () => {
    render(<Button type="submit">Save</Button>);
    expect(screen.getByRole("button")).toHaveAttribute("type", "submit");
  });

  it("is disabled and marked busy while loading", () => {
    render(<Button loading>Save</Button>);
    const button = screen.getByRole("button");
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute("aria-busy", "true");
  });

  it("cannot be activated while loading", async () => {
    const onClick = vi.fn();
    render(
      <Button loading onClick={onClick}>
        Save
      </Button>,
    );
    await userEvent.click(screen.getByRole("button"));
    expect(onClick).not.toHaveBeenCalled();
  });

  it("keeps its label in the DOM while loading, so width does not shift", () => {
    render(<Button loading>Submitting</Button>);
    expect(screen.getByRole("button")).toHaveTextContent("Submitting");
  });

  it("announces a loading label to screen readers", () => {
    render(
      <Button loading loadingLabel="Deleting account">
        Delete
      </Button>,
    );
    expect(screen.getByText("Deleting account")).toBeInTheDocument();
  });

  it("renders as the child element with asChild, preserving its content", () => {
    render(
      <Button asChild>
        <a href="/register">Get started</a>
      </Button>,
    );
    const link = screen.getByRole("link", { name: "Get started" });
    expect(link).toHaveAttribute("href", "/register");
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("marks an asChild link aria-disabled, since anchors cannot be disabled", () => {
    render(
      <Button asChild disabled>
        <a href="/register">Get started</a>
      </Button>,
    );
    const link = screen.getByRole("link");
    expect(link).toHaveAttribute("aria-disabled", "true");
    expect(link).toHaveAttribute("tabindex", "-1");
  });

  it("is reachable and activatable by keyboard", async () => {
    const onClick = vi.fn();
    render(<Button onClick={onClick}>Save</Button>);
    await userEvent.tab();
    expect(screen.getByRole("button")).toHaveFocus();
    await userEvent.keyboard("{Enter}");
    expect(onClick).toHaveBeenCalledTimes(1);
  });
});

describe("Field", () => {
  it("associates the label with the control", () => {
    render(
      <Field label="Email">
        <Input type="email" />
      </Field>,
    );
    expect(screen.getByLabelText("Email")).toBeInTheDocument();
  });

  it("links hint text via aria-describedby", () => {
    render(
      <Field label="Email" hint="We'll never share it.">
        <Input />
      </Field>,
    );
    const input = screen.getByLabelText("Email");
    const describedBy = input.getAttribute("aria-describedby");
    expect(describedBy).toBeTruthy();
    expect(document.getElementById(describedBy!)).toHaveTextContent(
      "We'll never share it.",
    );
  });

  it("marks the control invalid and links the error when one is present", () => {
    render(
      <Field label="Password" error="Too short.">
        <Input />
      </Field>,
    );
    const input = screen.getByLabelText("Password");
    expect(input).toHaveAttribute("aria-invalid", "true");
    const describedBy = input.getAttribute("aria-describedby") ?? "";
    const errorNode = describedBy
      .split(" ")
      .map((id) => document.getElementById(id))
      .find((node) => node?.textContent?.includes("Too short."));
    expect(errorNode).toBeTruthy();
  });

  it("announces errors via role=alert", () => {
    render(
      <Field label="Password" error="Too short.">
        <Input />
      </Field>,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("Too short.");
  });

  it("describes with both hint and error, in visual order", () => {
    render(
      <Field label="Password" hint="At least 8 characters." error="Too short.">
        <Input />
      </Field>,
    );
    const ids = (
      screen.getByLabelText("Password").getAttribute("aria-describedby") ?? ""
    ).split(" ");
    expect(ids).toHaveLength(2);
    expect(document.getElementById(ids[0])).toHaveTextContent(
      "At least 8 characters.",
    );
    expect(document.getElementById(ids[1])).toHaveTextContent("Too short.");
  });

  it("marks required controls with aria-required", () => {
    render(
      <Field label="Country" required>
        <Input />
      </Field>,
    );
    expect(screen.getByLabelText(/Country/)).toHaveAttribute(
      "aria-required",
      "true",
    );
  });

  it("propagates disabled to the control", () => {
    render(
      <Field label="Email" disabled>
        <Input />
      </Field>,
    );
    expect(screen.getByLabelText("Email")).toBeDisabled();
  });

  it("wires Textarea and Select the same way as Input", () => {
    render(
      <>
        <Field label="Bio">
          <Textarea />
        </Field>
        <Field label="Country">
          <Select>
            <option value="de">Germany</option>
          </Select>
        </Field>
      </>,
    );
    expect(screen.getByLabelText("Bio").tagName).toBe("TEXTAREA");
    expect(screen.getByLabelText("Country").tagName).toBe("SELECT");
  });

  it("keeps a hidden label available to assistive tech", () => {
    render(
      <Field label="Search" labelHidden>
        <Input />
      </Field>,
    );
    expect(screen.getByLabelText("Search")).toBeInTheDocument();
  });

  it("gives each Field a unique id when several are rendered", () => {
    render(
      <>
        <Field label="First">
          <Input />
        </Field>
        <Field label="Second">
          <Input />
        </Field>
      </>,
    );
    expect(screen.getByLabelText("First").id).not.toBe(
      screen.getByLabelText("Second").id,
    );
  });
});

describe("Checkbox", () => {
  it("exposes the checkbox role and reports its checked state", () => {
    render(<Checkbox checked onChange={() => {}} label="Agree" />);
    expect(screen.getByRole("checkbox", { name: "Agree" })).toBeChecked();
  });

  it("reports the next value, not the event", async () => {
    const onChange = vi.fn();
    render(<Checkbox checked={false} onChange={onChange} label="Agree" />);
    await userEvent.click(screen.getByRole("checkbox"));
    expect(onChange).toHaveBeenCalledWith(true);
  });

  it("toggles with the keyboard", async () => {
    function Harness() {
      const [on, setOn] = useState(false);
      return <Checkbox checked={on} onChange={setOn} label="Agree" />;
    }
    render(<Harness />);
    await userEvent.tab();
    await userEvent.keyboard(" ");
    expect(screen.getByRole("checkbox")).toBeChecked();
  });

  it("takes its accessible name from visible children when present", () => {
    render(<Checkbox checked onChange={() => {}}>Enable reminders</Checkbox>);
    expect(
      screen.getByRole("checkbox", { name: "Enable reminders" }),
    ).toBeInTheDocument();
  });

  it("exposes the indeterminate state as mixed", () => {
    render(<Checkbox indeterminate checked={false} onChange={() => {}} label="All" />);
    expect(screen.getByRole("checkbox")).toBePartiallyChecked();
  });

  it("does not fire when disabled", async () => {
    const onChange = vi.fn();
    render(
      <Checkbox checked={false} onChange={onChange} disabled label="Agree" />,
    );
    await userEvent.click(screen.getByRole("checkbox"));
    expect(onChange).not.toHaveBeenCalled();
  });
});

describe("Switch", () => {
  it("uses the switch role rather than checkbox", () => {
    render(<Switch checked onChange={() => {}} label="Notifications" />);
    expect(
      screen.getByRole("switch", { name: "Notifications" }),
    ).toBeChecked();
  });

  it("toggles with Space", async () => {
    function Harness() {
      const [on, setOn] = useState(false);
      return <Switch checked={on} onChange={setOn} label="Notifications" />;
    }
    render(<Harness />);
    await userEvent.tab();
    await userEvent.keyboard(" ");
    expect(screen.getByRole("switch")).toBeChecked();
  });
});

describe("Progress", () => {
  it("exposes value, bounds and an accessible name", () => {
    render(<Progress value={40} label="Upload" />);
    const bar = screen.getByRole("progressbar", { name: "Upload" });
    expect(bar).toHaveAttribute("aria-valuenow", "40");
    expect(bar).toHaveAttribute("aria-valuemin", "0");
    expect(bar).toHaveAttribute("aria-valuemax", "100");
  });

  it("clamps out-of-range values instead of overflowing the track", () => {
    render(<Progress value={150} label="Upload" />);
    expect(screen.getByRole("progressbar")).toHaveAttribute(
      "aria-valuenow",
      "100",
    );
  });

  it("clamps negative values to zero", () => {
    render(<Progress value={-20} label="Upload" />);
    expect(screen.getByRole("progressbar")).toHaveAttribute(
      "aria-valuenow",
      "0",
    );
  });

  it("prefers a human-readable value when supplied", () => {
    render(
      <Progress value={2} max={4} label="Onboarding" valueText="Step 2 of 4" />,
    );
    expect(screen.getByRole("progressbar")).toHaveAttribute(
      "aria-valuetext",
      "Step 2 of 4",
    );
  });

  it("survives a zero max without dividing by zero", () => {
    render(<Progress value={1} max={0} label="Broken" />);
    expect(screen.getByRole("progressbar")).toBeInTheDocument();
  });
});

describe("Alert", () => {
  it("announces danger assertively", () => {
    render(<Alert tone="danger" title="Failed" />);
    expect(screen.getByRole("alert")).toHaveTextContent("Failed");
  });

  it("announces other tones politely", () => {
    render(<Alert tone="success" title="Saved" />);
    expect(screen.getByRole("status")).toHaveTextContent("Saved");
  });

  it("can opt out of announcement for statically rendered alerts", () => {
    render(<Alert tone="danger" title="Failed" announce="none" />);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("only shows a dismiss control when a handler is supplied", async () => {
    const onDismiss = vi.fn();
    const { rerender } = render(<Alert tone="info" title="Note" />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();

    rerender(<Alert tone="info" title="Note" onDismiss={onDismiss} />);
    await userEvent.click(screen.getByRole("button", { name: "Dismiss" }));
    expect(onDismiss).toHaveBeenCalledTimes(1);
  });
});

describe("Badge", () => {
  it("is a plain span with no role by default", () => {
    render(<Badge>Free</Badge>);
    expect(screen.getByText("Free").tagName).toBe("SPAN");
  });

  it("becomes a live status region only when asked", () => {
    render(<Badge live>Recording</Badge>);
    expect(screen.getByRole("status")).toHaveTextContent("Recording");
  });
});

describe("Heading", () => {
  it("keeps semantic level independent of visual size", () => {
    render(
      <Heading as="h1" size="xs">
        Small but top-level
      </Heading>,
    );
    expect(
      screen.getByRole("heading", { level: 1, name: "Small but top-level" }),
    ).toBeInTheDocument();
  });
});
