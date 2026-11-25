// @vitest-environment happy-dom
import { describe, it, expect } from "vitest";
import { ApiError } from "./api";
import {
  absoluteUrl,
  authErrorMessage,
  sanitizeNextPath,
  signUpFieldErrors,
  BANNED_MESSAGE,
  RATE_LIMITED_MESSAGE,
  INVITE_INVALID_MESSAGE,
} from "./auth-errors";

describe("sanitizeNextPath", () => {
  it("accepts same-origin relative paths", () => {
    expect(sanitizeNextPath("/")).toBe("/");
    expect(sanitizeNextPath("/forge/packs")).toBe("/forge/packs");
    expect(sanitizeNextPath("/play?session=abc")).toBe("/play?session=abc");
  });

  it("rejects absolute URLs", () => {
    expect(sanitizeNextPath("https://evil.example/steal")).toBeNull();
    expect(sanitizeNextPath("http://evil.example")).toBeNull();
    expect(sanitizeNextPath("javascript:alert(1)")).toBeNull();
  });

  it("rejects protocol-relative and backslash tricks", () => {
    expect(sanitizeNextPath("//evil.example")).toBeNull();
    expect(sanitizeNextPath("/\\evil.example")).toBeNull();
    expect(sanitizeNextPath("/path\\with\\backslash")).toBeNull();
  });

  it("rejects non-strings, empty strings and control characters", () => {
    expect(sanitizeNextPath(null)).toBeNull();
    expect(sanitizeNextPath(undefined)).toBeNull();
    expect(sanitizeNextPath(42)).toBeNull();
    expect(sanitizeNextPath("")).toBeNull();
    expect(sanitizeNextPath("/path\u0000")).toBeNull();
    expect(sanitizeNextPath("/path\nSet-Cookie: x")).toBeNull();
  });
});

describe("authErrorMessage", () => {
  it("has distinct banned (403) and rate-limited (429) messages", () => {
    const banned = authErrorMessage(new ApiError(403, '{"detail":"Forbidden"}'), "login");
    const limited = authErrorMessage(new ApiError(429, '{"detail":"slow down"}'), "login");
    expect(banned).toBe(BANNED_MESSAGE);
    expect(limited).toBe(RATE_LIMITED_MESSAGE);
    expect(banned).not.toBe(limited);
  });

  it("does not call a CSRF failure a ban", () => {
    expect(authErrorMessage(new ApiError(403, '{"detail":"Missing or invalid CSRF token."}'), "login"))
      .toMatch(/refresh/i);
  });

  it("maps invite rejections on sign-up to the invite message", () => {
    expect(authErrorMessage(new ApiError(403, '{"detail":"invite token required"}'), "signup"))
      .toBe(INVITE_INVALID_MESSAGE);
    expect(authErrorMessage(new ApiError(400, '{"detail":"invalid invite"}'), "signup"))
      .toMatch(/invite/i);
  });

  it("reports 401 on login as bad credentials", () => {
    expect(authErrorMessage(new ApiError(401, '{"detail":"Not authenticated"}'), "login"))
      .toBe("Invalid login or password.");
  });

  it("keeps 409 and 422 sign-up messages distinct", () => {
    expect(authErrorMessage(new ApiError(409, "conflict"), "signup")).toMatch(/already exists/i);
    expect(authErrorMessage(new ApiError(422, "bad"), "signup")).toMatch(/check the form/i);
  });

  it("tells the user an expired reset link needs a new one", () => {
    expect(authErrorMessage(new ApiError(410, '{"detail":"token expired"}'), "reset"))
      .toMatch(/expired/i);
    expect(authErrorMessage(new ApiError(400, '{"detail":"bad token"}'), "reset"))
      .toMatch(/invalid or has expired/i);
  });
});

describe("signUpFieldErrors", () => {
  it("parses FastAPI 422 validation lists by loc", () => {
    const err = new ApiError(
      422,
      JSON.stringify([
        { loc: ["body", "email"], msg: "value is not a valid email address" },
        { loc: ["body", "password"], msg: "String should have at least 12 characters" },
      ]),
    );
    expect(signUpFieldErrors(err)).toEqual({
      email: "value is not a valid email address",
      password: "String should have at least 12 characters",
    });
  });

  it("parses {detail: {field: message}} objects and maps invite_token", () => {
    const err = new ApiError(400, JSON.stringify({ detail: { invite_token: "expired" } }));
    expect(signUpFieldErrors(err)).toEqual({ invite: "expired" });
  });

  it("uses keyword matching for plain 400 detail strings", () => {
    const err = new ApiError(400, JSON.stringify({ detail: "username already taken" }));
    expect(signUpFieldErrors(err)).toHaveProperty("username");
  });

  it("returns null for form-level statuses and non-API errors", () => {
    expect(signUpFieldErrors(new ApiError(409, '{"detail":"already exists"}'))).toBeNull();
    expect(signUpFieldErrors(new ApiError(429, "slow down"))).toBeNull();
    expect(signUpFieldErrors(new Error("boom"))).toBeNull();
    expect(signUpFieldErrors(new ApiError(422, "not json at all"))).toBeNull();
  });
});

describe("absoluteUrl", () => {
  it("prefixes the browser origin (happy-dom origin)", () => {
    expect(absoluteUrl("/login?invite=abc")).toBe(`${window.location.origin}/login?invite=abc`);
  });
});
