import { describe, expect, it } from "vitest";
import { emailInitials, emailGreetingName } from "@/lib/user-display";

describe("emailInitials", () => {
  it("takes the first letter of the first two dot-separated segments", () => {
    expect(emailInitials("jane.doe@example.com")).toBe("JD");
  });

  it("falls back to the first two characters when there's only one segment", () => {
    expect(emailInitials("amina@example.com")).toBe("AM");
  });

  it("treats underscores and hyphens the same as dots", () => {
    expect(emailInitials("jane_doe@example.com")).toBe("JD");
    expect(emailInitials("jane-doe@example.com")).toBe("JD");
  });

  it("returns a placeholder for an address with no local part", () => {
    expect(emailInitials("@example.com")).toBe("?");
  });
});

describe("emailGreetingName", () => {
  it("turns a dotted local part into a capitalised full name", () => {
    expect(emailGreetingName("amina.hassan@example.com")).toBe("Amina Hassan");
  });

  it("strips trailing digits", () => {
    expect(emailGreetingName("jane_doe97@example.com")).toBe("Jane Doe");
  });

  it("falls back to the raw email when nothing alphabetic remains", () => {
    expect(emailGreetingName("12345@example.com")).toBe("12345@example.com");
  });
});
