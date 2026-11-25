import { describe, it, expect } from "vitest";
import { ApiError } from "@/lib/api";
import {
  QUOTA_MESSAGE,
  isQuotaDetail,
  isQuotaError,
  quotaMessageFor,
  friendlyTurnFailure,
} from "./quota";

describe("quota helpers", () => {
  it("recognises an ApiError 429 as a quota error", () => {
    const err = new ApiError(429, '{"detail":"daily cap"}');
    expect(isQuotaError(err)).toBe(true);
    expect(quotaMessageFor(err)).toBe(QUOTA_MESSAGE);
    expect(QUOTA_MESSAGE).toBe(
      "Daily limit reached - resets 00:00 UTC. Ask your admin to raise it.",
    );
  });

  it("passes non-429 errors through as null", () => {
    expect(isQuotaError(new ApiError(500, "boom"))).toBe(false);
    expect(quotaMessageFor(new ApiError(500, "boom"))).toBe(null);
    expect(quotaMessageFor(new Error("plain"))).toBe(null);
    expect(quotaMessageFor(undefined)).toBe(null);
  });

  it("detects quota text in raw response bodies", () => {
    expect(isQuotaDetail('{"detail":"Quota exceeded for owner"}')).toBe(true);
    expect(isQuotaDetail("HTTP 429 Too Many Requests")).toBe(true);
    expect(isQuotaDetail("daily limit reached")).toBe(true);
    expect(isQuotaDetail("rate limit hit")).toBe(true);
    expect(isQuotaDetail("connection refused")).toBe(false);
  });

  it("rewrites only quota failures on the turn-failure card", () => {
    expect(
      friendlyTurnFailure({ text: "act", detail: '{"detail":"quota exceeded"}' }),
    ).toEqual({ text: "act", detail: QUOTA_MESSAGE });
    expect(
      friendlyTurnFailure({ text: "act", detail: "The GM didn't respond in time." }),
    ).toEqual({ text: "act", detail: "The GM didn't respond in time." });
    expect(friendlyTurnFailure(null)).toBeNull();
  });
});
