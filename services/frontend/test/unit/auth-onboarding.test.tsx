import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { apiErrorMessage, isSubscriptionRequired } from "@/lib/api";
import { OnboardingStepper } from "@/components/onboarding/onboarding-stepper";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

const authApiMocks = vi.hoisted(() => ({
  register: vi.fn(),
  forgotPassword: vi.fn(),
}));

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    authApi: { ...actual.authApi, ...authApiMocks },
  };
});

// Imported after the mocks above so the components pick up the mocked module.
const { default: RegisterForm } = await import("@/components/auth/RegisterForm");
const { default: ForgotPasswordForm } = await import("@/components/auth/ForgotPasswordForm");
const { default: ResetPasswordForm } = await import("@/components/auth/ResetPasswordForm");

describe("lib/api error helpers", () => {
  it("extracts a string message from the Gateway/User-service error shape", () => {
    const err = { response: { data: { message: "Email already registered." } } };
    expect(apiErrorMessage(err)).toBe("Email already registered.");
  });

  it("joins class-validator's array message shape", () => {
    const err = { response: { data: { message: ["GPA cannot exceed 100."] } } };
    expect(apiErrorMessage(err)).toBe("GPA cannot exceed 100.");
  });

  it("returns undefined for a shape it doesn't recognise", () => {
    expect(apiErrorMessage(new Error("network down"))).toBeUndefined();
  });

  it("recognises the Gateway's subscription_required 403", () => {
    const err = { response: { status: 403, data: { error: "subscription_required" } } };
    expect(isSubscriptionRequired(err)).toBe(true);
  });

  it("does not misclassify an unrelated 403", () => {
    const err = { response: { status: 403, data: { message: "forbidden" } } };
    expect(isSubscriptionRequired(err)).toBe(false);
  });
});

describe("RegisterForm", () => {
  it("blocks submission and never calls the API when passwords don't match", async () => {
    const user = userEvent.setup();
    render(<RegisterForm />);

    await user.type(screen.getByLabelText(/^email/i), "student@example.com");
    await user.type(screen.getByLabelText(/^password/i), "correct-horse");
    await user.type(screen.getByLabelText(/confirm password/i), "different");
    await user.click(screen.getByRole("button", { name: /create account/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/do not match/i);
    expect(authApiMocks.register).not.toHaveBeenCalled();
  });
});

describe("ForgotPasswordForm", () => {
  it("shows a non-revealing success state after requesting a reset link", async () => {
    authApiMocks.forgotPassword.mockResolvedValueOnce({});
    const user = userEvent.setup();
    render(<ForgotPasswordForm />);

    await user.type(screen.getByLabelText(/^email/i), "student@example.com");
    await user.click(screen.getByRole("button", { name: /send reset link/i }));

    await waitFor(() => {
      expect(screen.getByRole("status")).toHaveTextContent(/if an account exists/i);
    });
    // Never confirms or denies the address exists, by design.
    expect(screen.queryByText(/no account found/i)).not.toBeInTheDocument();
  });
});

describe("ResetPasswordForm", () => {
  it("shows an invalid-link state instead of a form when no token is present", () => {
    render(<ResetPasswordForm token={null} />);

    // Rendered with announce="none": this is the page's initial content, not
    // a dynamic change, so it isn't wired as a live region -- consistent with
    // Alert's own documented convention (components/ui/alert.tsx).
    expect(screen.getByText("This link is invalid")).toBeInTheDocument();
    expect(screen.queryByLabelText(/new password/i)).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: /request a new link/i })).toHaveAttribute(
      "href",
      "/forgot-password",
    );
  });
});

describe("OnboardingStepper", () => {
  it("exposes progress to assistive technology instead of only a styled bar", () => {
    render(<OnboardingStepper currentStep={2} />);

    const bar = screen.getByRole("progressbar");
    expect(bar).toHaveAttribute("aria-valuenow", "2");
    expect(bar).toHaveAttribute("aria-valuemax", "4");
    expect(bar).toHaveAttribute("aria-valuetext", "Step 2 of 4");
  });
});
