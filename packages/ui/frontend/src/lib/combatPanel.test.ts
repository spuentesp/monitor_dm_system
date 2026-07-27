import { describe, it, expect } from "vitest";
import { flattenStats, readProgression } from "./combatPanel";

describe("flattenStats", () => {
  it("keeps top-level numbers and underscores → spaces", () => {
    expect(flattenStats({ hit_points: 7 })).toEqual({ "hit points": 7 });
  });

  it("reads .current from resource objects", () => {
    expect(flattenStats({ Health: { current: 11, max: 12 } })).toEqual({ Health: 11 });
  });

  it("expands nested numeric fields when there is no .current", () => {
    expect(flattenStats({ pools: { mana_now: 3, focus: 2 } })).toEqual({
      "pools mana now": 3,
      "pools focus": 2,
    });
  });

  it("ignores arrays and non-numeric values", () => {
    expect(flattenStats({ tags: ["wounded"], note: "x", hp: 5 })).toEqual({ hp: 5 });
  });
});

describe("readProgression", () => {
  it("returns null when there is no xp or level", () => {
    expect(readProgression({ Health: { current: 10, max: 10 } })).toBeNull();
  });

  it("reads a flat xp number", () => {
    expect(readProgression({ xp: 120 })).toEqual({ xp: 120, xpMax: undefined, level: undefined });
  });

  it("reads xp.current and xp.next as max", () => {
    expect(readProgression({ experience: { current: 50, next: 100 } })).toEqual({
      xp: 50,
      xpMax: 100,
      level: undefined,
    });
  });

  it("captures level from *_level keys", () => {
    expect(readProgression({ char_level: 3 })).toEqual({ xp: undefined, xpMax: undefined, level: 3 });
  });
});
