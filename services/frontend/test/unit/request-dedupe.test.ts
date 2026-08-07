import { describe, expect, it, vi } from "vitest";
import { dedupe } from "@/lib/request-dedupe";

describe("dedupe", () => {
  it("collapses concurrent calls for the same key into one underlying call", async () => {
    let calls = 0;
    const fn = () => {
      calls += 1;
      return Promise.resolve(calls);
    };

    const [a, b, c] = await Promise.all([
      dedupe("key", fn),
      dedupe("key", fn),
      dedupe("key", fn),
    ]);

    expect(calls).toBe(1);
    expect([a, b, c]).toEqual([1, 1, 1]);
  });

  it("does not collapse calls for different keys", async () => {
    const fn = vi.fn().mockResolvedValue("value");

    await Promise.all([dedupe("a", fn), dedupe("b", fn)]);

    expect(fn).toHaveBeenCalledTimes(2);
  });

  it("issues a fresh call once the in-flight one has settled", async () => {
    const fn = vi.fn().mockResolvedValue("value");

    await dedupe("key", fn);
    await dedupe("key", fn);

    expect(fn).toHaveBeenCalledTimes(2);
  });

  it("does not cache a rejection -- the next call gets a fresh attempt", async () => {
    const fn = vi
      .fn()
      .mockRejectedValueOnce(new Error("network down"))
      .mockResolvedValueOnce("recovered");

    await expect(dedupe("key", fn)).rejects.toThrow("network down");
    await expect(dedupe("key", fn)).resolves.toBe("recovered");
  });
});
