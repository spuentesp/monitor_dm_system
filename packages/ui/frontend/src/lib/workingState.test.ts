import { describe, it, expect } from "vitest";
import { workingStateChips } from "./workingState";

describe("workingStateChips", () => {
  it("renders scalar stats as stat chips", () => {
    expect(workingStateChips({ grit: 12, name: "Lantern" })).toEqual([
      { label: "grit", value: "12", kind: "stat" },
      { label: "name", value: "Lantern", kind: "stat" },
    ]);
  });

  it("renders current/max objects as a single stat chip", () => {
    expect(workingStateChips({ Health: { current: 11, max: 12 } })).toEqual([
      { label: "Health", value: "11/12", kind: "stat" },
    ]);
  });

  it("renders array values as tag chips (max 6) with underscores → spaces", () => {
    const chips = workingStateChips({ conditions: ["off_balance", "wounded"] });
    expect(chips).toEqual([
      { label: "off balance", value: "", kind: "tag" },
      { label: "wounded", value: "", kind: "tag" },
    ]);
  });

  it("expands nested scalar fields when no current/max present", () => {
    expect(workingStateChips({ pools: { mana: 3 } })).toEqual([
      { label: "pools mana", value: "3", kind: "stat" },
    ]);
  });

  it("caps the total number of chips at 14", () => {
    const big: Record<string, number> = {};
    for (let i = 0; i < 30; i++) big[`s${i}`] = i;
    expect(workingStateChips(big)).toHaveLength(14);
  });
});
