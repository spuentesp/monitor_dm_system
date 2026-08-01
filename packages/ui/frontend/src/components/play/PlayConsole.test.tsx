import { describe, it, expect } from "vitest";
import { shouldShowBeginStory, wrapOutgoingMessageForOoc } from "./PlayConsole";

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

describe("shouldShowBeginStory", () => {
  it("shows once the Session Zero summary is the latest GM message", () => {
    expect(
      shouldShowBeginStory("session_zero", { type: "story_agreements_summary" }),
    ).toBe(true);
  });

  it("stays hidden while Session Zero questions are still in flight", () => {
    expect(
      shouldShowBeginStory("session_zero", { type: "story_agreements_question" }),
    ).toBe(false);
  });

  it("stays hidden outside the session_zero phase even with a summary", () => {
    expect(
      shouldShowBeginStory("active_play", { type: "story_agreements_summary" }),
    ).toBe(false);
  });

  it("stays hidden with no GM metadata yet", () => {
    expect(shouldShowBeginStory("session_zero", undefined)).toBe(false);
    expect(shouldShowBeginStory("session_zero", {})).toBe(false);
  });
});
