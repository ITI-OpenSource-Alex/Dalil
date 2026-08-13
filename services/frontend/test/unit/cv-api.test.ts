import { describe, it, expect, vi, afterEach } from "vitest";
import { getLatestCv, streamCvReview, uploadCv } from "@/lib/cv-api";
import { isSubscriptionRequiredError } from "@/lib/subscription";

describe("getLatestCv", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("returns null on a 404 instead of throwing -- no CV uploaded yet is expected, not a fault", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ status: 404, ok: false });
    vi.stubGlobal("fetch", fetchMock);

    await expect(getLatestCv()).resolves.toBeNull();
  });

  it("returns the parsed body on success", async () => {
    const body = {
      cvId: 1,
      s3Key: "cvs/user-1/resume.pdf",
      originalFilename: "resume.pdf",
      status: "ready",
      uploadedAt: "2026-01-01T00:00:00Z",
    };
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => body,
    });
    vi.stubGlobal("fetch", fetchMock);

    await expect(getLatestCv()).resolves.toEqual(body);
  });
});

describe("uploadCv", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("posts multipart form data with credentials included", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ cvId: 1, status: "processing", s3Key: "cvs/user-1/resume.pdf" }),
    });
    vi.stubGlobal("fetch", fetchMock);

    const file = new File(["%PDF-1.7"], "resume.pdf", { type: "application/pdf" });
    await uploadCv(file);

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/api/writing/cv/upload"),
      expect.objectContaining({ method: "POST", credentials: "include" }),
    );
    const body = fetchMock.mock.calls[0][1].body as FormData;
    expect(body.get("file")).toBe(file);
  });

  it("rejects with a SubscriptionRequiredError on a 403 -- a real fault would be surprising here since upload is free-tier, but the client must still handle it", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 403,
      text: async () => JSON.stringify({ error: "subscription_required" }),
    });
    vi.stubGlobal("fetch", fetchMock);

    const file = new File(["%PDF-1.7"], "resume.pdf", { type: "application/pdf" });
    await expect(uploadCv(file)).rejects.toSatisfy(isSubscriptionRequiredError);
  });
});

describe("streamCvReview", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("delivers section and complete events, including a trailing complete with no closing blank line", async () => {
    const encoder = new TextEncoder();
    const body =
      'event: section\ndata: {"name":"Skills","score":80,"issues":[],"suggestions":[]}\n\n' +
      'event: complete\ndata: {"overallScore":78,"sections":[{"name":"Skills","score":80,"issues":[],"suggestions":[]}]}\n';
    let sent = false;
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      body: {
        getReader: () => ({
          read: async () => {
            if (sent) return { done: true, value: undefined };
            sent = true;
            return { done: false, value: encoder.encode(body) };
          },
        }),
      },
    });
    vi.stubGlobal("fetch", fetchMock);

    const events: string[] = [];
    await streamCvReview(
      { cvS3Key: "cvs/user-1/resume.pdf", targetCountry: "Germany", targetField: "CS" },
      (event) => events.push(event.type),
    );

    expect(events).toEqual(["section", "complete"]);
  });

  it("rejects with a SubscriptionRequiredError on the Gateway's paid-tier 403", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 403,
      text: async () =>
        JSON.stringify({ error: "subscription_required", upgradeUrl: "https://billing.example/upgrade" }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      streamCvReview(
        { cvS3Key: "cvs/user-1/resume.pdf", targetCountry: "Germany", targetField: "CS" },
        () => {},
      ),
    ).rejects.toSatisfy(isSubscriptionRequiredError);
  });
});
