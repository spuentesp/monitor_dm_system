// @vitest-environment happy-dom
import { describe, it, expect, beforeEach } from "vitest";
import { readPanelPrefs, writePanelPrefs, visibleOrderedPanels } from "./gm-panel-prefs";

beforeEach(() => {
  window.localStorage.clear();
});

describe("gm-panel-prefs", () => {
  it("defaults to the given order with nothing hidden", () => {
    const ids = ["ask-world", "hooks", "dice"];
    expect(visibleOrderedPanels(ids, readPanelPrefs())).toEqual(ids);
  });

  it("persists hidden panels and order to localStorage", () => {
    writePanelPrefs({ order: ["dice", "hooks", "ask-world"], hidden: ["hooks"] });
    const ids = ["ask-world", "hooks", "dice"];
    expect(visibleOrderedPanels(ids, readPanelPrefs())).toEqual(["dice", "ask-world"]);
  });

  it("ignores stored ids that no longer exist and appends new ones", () => {
    writePanelPrefs({ order: ["ghost", "dice"], hidden: [] });
    expect(visibleOrderedPanels(["ask-world", "dice"], readPanelPrefs())).toEqual([
      "dice",
      "ask-world",
    ]);
  });

  it("tolerates corrupt JSON in localStorage", () => {
    window.localStorage.setItem("monitor.gm.panelOrder", "{not json");
    expect(readPanelPrefs()).toEqual({ order: [], hidden: [] });
  });
});
