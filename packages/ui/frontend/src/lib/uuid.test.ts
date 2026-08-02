import { describe, it, expect } from "vitest";
import { uuid } from "./uuid";

describe("uuid", () => {
  it("returns a v4-shaped string", () => {
    const id = uuid();
    expect(id).toMatch(
      /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i,
    );
  });

  it("falls back when crypto.randomUUID is missing (LAN HTTP, old browsers)", () => {
    // `globalThis.crypto` is a getter-only property in Node, so we override
    // it via defineProperty to simulate a non-secure context (LAN HTTP,
    // older browsers) where `crypto.randomUUID` is not present.
    const originalDescriptor = Object.getOwnPropertyDescriptor(globalThis, "crypto");
    Object.defineProperty(globalThis, "crypto", {
      configurable: true,
      value: { getRandomValues: undefined },
    });

    try {
      const id = uuid();
      expect(id).toMatch(
        /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i,
      );
    } finally {
      if (originalDescriptor) {
        Object.defineProperty(globalThis, "crypto", originalDescriptor);
      } else {
        // Fall back to deleting our override so subsequent tests aren't
        // affected even though `delete` on a non-configurable property
        // would throw — we set configurable: true above.
        delete (globalThis as { crypto?: unknown }).crypto;
      }
    }
  });

  it("produces unique ids in a tight loop", () => {
    const ids = new Set<string>();
    for (let i = 0; i < 1000; i++) ids.add(uuid());
    expect(ids.size).toBe(1000);
  });
});
