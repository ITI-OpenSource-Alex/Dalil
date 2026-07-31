import { describe, it, expect } from "vitest";
import { phaseForItem } from "@/lib/checklist-phases";

describe("phaseForItem", () => {
  it("maps language-related categories to Language Prep", () => {
    expect(phaseForItem("language", "ielts_retake")).toBe("Language Prep");
    expect(phaseForItem(null, "retake_ielts_exam")).toBe("Language Prep");
  });

  it("maps document-related categories to Documents", () => {
    expect(phaseForItem("documents", "valid_passport")).toBe("Documents");
    expect(phaseForItem(null, "recommendation_letters")).toBe("Documents");
  });

  it("maps acceptance-related categories to Post-acceptance", () => {
    expect(phaseForItem("administrative", "confirm_enrollment")).toBe(
      "Post-acceptance",
    );
  });

  it("never returns Financial Requirements, even for a financial-sounding category", () => {
    // GOA-035 AC: Financial Requirements must only ever come from the structured
    // backend endpoint, never from an LLM-authored checklist item category.
    const result = phaseForItem("financial", "financial_proof");
    expect(result).not.toBe("Financial Requirements");
  });

  it("falls back to Application for unrecognized categories", () => {
    expect(phaseForItem("administrative", "application_fee")).toBe("Application");
    expect(phaseForItem("something_unexpected", "mystery_item")).toBe("Application");
  });
});
