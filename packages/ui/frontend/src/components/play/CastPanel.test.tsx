import { describe, it, expect } from "vitest";

import { filterCastNpcs, speakerBadge } from "./CastPanel";

describe("speakerBadge", () => {
  it("marks the session speaker as speaking", () => {
    expect(speakerBadge("a", "a", "a")).toBe("speaking");
  });

  it("marks a panel pick that is not yet applied as speaks next", () => {
    expect(speakerBadge("b", "b", "a")).toBe("speaks next");
  });

  it("shows no badge on non-speaker rows", () => {
    expect(speakerBadge("c", "a", "a")).toBeNull();
  });
});

describe("filterCastNpcs", () => {
  const npcs = [
    { id: "n1", name: "Vex", universe_id: "u1" },
    { id: "n2", name: "Tomas", universe_id: "u2" },
    { id: "n3", name: "Mira", universe_id: "u1" },
  ];

  it("keeps only the session universe's NPCs", () => {
    expect(filterCastNpcs(npcs, "u1")).toEqual([
      { id: "n1", name: "Vex" },
      { id: "n3", name: "Mira" },
    ]);
  });

  it("lists everything when no universe is bound", () => {
    expect(filterCastNpcs(npcs, null)).toHaveLength(3);
  });

  it("caps the GM-controlled list", () => {
    expect(filterCastNpcs(npcs, null, 2)).toHaveLength(2);
  });
});
