import { describe, it, expect } from "vitest";
import { ApiError } from "@/lib/api";
import {
  RATE_LIMIT_MESSAGE,
  isRateLimit,
  gmErrorMessage,
  gmErrorText,
} from "./gmErrors";

describe("gm 429 error helper", () => {
  it("turns ApiError 429 into the daily-limit copy, verbatim", () => {
    const err = new ApiError(429, '{"detail":"quota"}');
    expect(isRateLimit(err)).toBe(true);
    expect(gmErrorMessage(err, "Failed to generate hooks. Try again.")).toBe(
      "Daily limit reached - resets 00:00 UTC. Ask your admin to raise it.",
    );
    expect(RATE_LIMIT_MESSAGE).toBe(
      "Daily limit reached - resets 00:00 UTC. Ask your admin to raise it.",
    );
  });

  it("keeps the panel fallback for any other error", () => {
    expect(gmErrorMessage(new ApiError(500, "boom"), "Try again.")).toBe("Try again.");
    expect(gmErrorMessage(new Error("network"), "Try again.")).toBe("Try again.");
    expect(gmErrorMessage(undefined, "Try again.")).toBe("Try again.");
    expect(isRateLimit(new Error("nope"))).toBe(false);
  });

  it("gmErrorText extracts text but still swaps in the limit copy", () => {
    expect(gmErrorText(new ApiError(429, "raw"))).toBe(RATE_LIMIT_MESSAGE);
    expect(gmErrorText(new Error("bad input"))).toBe("bad input");
  });
});
