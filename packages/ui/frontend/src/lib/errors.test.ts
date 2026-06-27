import { describe, it, expect } from "vitest";
import { errorMessage } from "./errors";

describe("errorMessage", () => {
  it("returns the string itself when given a string", () => {
    expect(errorMessage("boom")).toBe("boom");
  });

  it("extracts .message from Error", () => {
    expect(errorMessage(new Error("nope"))).toBe("nope");
  });

  it("extracts .message from a DOMException-shaped object", () => {
    expect(errorMessage({ message: "rate-limited" })).toBe("rate-limited");
  });

  it("falls back to JSON.stringify for plain objects without .message", () => {
    const result = errorMessage({ code: 42, detail: "bad" });
    expect(result).toContain("42");
    expect(result).toContain("bad");
  });

  it("handles null and undefined", () => {
    expect(errorMessage(null)).toBe("null");
    expect(errorMessage(undefined)).toBe("undefined");
  });

  it("handles a circular object without throwing", () => {
    const a: Record<string, unknown> = {};
    a.self = a;
    // Should not throw; should produce something stringifiable.
    expect(() => errorMessage(a)).not.toThrow();
    expect(typeof errorMessage(a)).toBe("string");
  });
});
