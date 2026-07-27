import { describe, it, expect } from "vitest";
import { wrapOutgoingMessageForOoc } from "./PlayConsole";

describe("wrapOutgoingMessageForOoc", () => {
  it("wraps the message in ((...)) when in OOC mode with no selected character", () => {
    expect(
      wrapOutgoingMessageForOoc("what's my HP again?", {
        chatMode: "ooc",
        hasSelectedCharacter: false,
      }),
    ).toBe("((what's my HP again?))");
  });

  it("leaves the message untouched in IC mode", () => {
    expect(
      wrapOutgoingMessageForOoc("I draw my sword.", {
        chatMode: "ic",
        hasSelectedCharacter: false,
      }),
    ).toBe("I draw my sword.");
  });

  it("leaves the message untouched when a persona character is selected, even in OOC mode", () => {
    // chatMode='ooc' + a selected character routes through the separate
    // chat_mode='ooc' character-chat path via send options instead.
    expect(
      wrapOutgoingMessageForOoc("what's your backstory?", {
        chatMode: "ooc",
        hasSelectedCharacter: true,
      }),
    ).toBe("what's your backstory?");
  });

  it("does not double-wrap a message the player already wrapped themselves", () => {
    expect(
      wrapOutgoingMessageForOoc("((already OOC))", {
        chatMode: "ooc",
        hasSelectedCharacter: false,
      }),
    ).toBe("((already OOC))");
  });

  it("trims whitespace before wrapping", () => {
    expect(
      wrapOutgoingMessageForOoc("  can I use fire magic here?  ", {
        chatMode: "ooc",
        hasSelectedCharacter: false,
      }),
    ).toBe("((can I use fire magic here?))");
  });
});
