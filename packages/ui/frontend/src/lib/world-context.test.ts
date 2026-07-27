/**
 * repairWorldSelection (F3-3 phase 7): deleting the selected universe or
 * multiverse must repair the persisted WorldContext selection.
 */

import { describe, it, expect } from "vitest";
import { repairWorldSelection, type WorldSelection } from "./world-context";

const SEL: WorldSelection = {
  multiverseId: "mv-1",
  universeId: "u-1",
  universeLabel: "Ashen Vale",
};

describe("repairWorldSelection", () => {
  it("clears everything when the selected multiverse is deleted", () => {
    expect(repairWorldSelection(SEL, { multiverseId: "mv-1" })).toEqual({
      multiverseId: null,
      universeId: null,
      universeLabel: null,
    });
  });

  it("clears only the universe when the selected universe is deleted", () => {
    expect(repairWorldSelection(SEL, { universeId: "u-1" })).toEqual({
      multiverseId: "mv-1",
      universeId: null,
      universeLabel: null,
    });
  });

  it("leaves unrelated selections untouched", () => {
    expect(repairWorldSelection(SEL, { multiverseId: "mv-other" })).toEqual(SEL);
    expect(repairWorldSelection(SEL, { universeId: "u-other" })).toEqual(SEL);
  });
});
