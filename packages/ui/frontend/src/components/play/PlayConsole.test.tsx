import { describe, it, expect } from "vitest";
import { extractTurnImageSuggestions, shouldShowBeginStory, wrapOutgoingMessageForOoc } from "./PlayConsole";

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


// ─── Image suggestions (Task 9) ──────────────────────────────────────

describe("extractTurnImageSuggestions", () => {
  const currentTurnSuggestion = {
    suggestion_id: "11111111-1111-4111-8111-111111111111",
    asset_type: "location",
    subject_entity_ids: ["22222222-2222-4222-8222-222222222222"],
    reason: "location_change",
    aspect_ratio: "16:9",
    source_turn_id: "turn-9",
  };
  const olderTurnSuggestion = {
    ...currentTurnSuggestion,
    suggestion_id: "33333333-3333-4333-8333-333333333333",
    reason: "climax",
    source_turn_id: "turn-6",
  };

  it("returns only the suggestions sourced from this turn", () => {
    // metadata.image_suggestions accumulates over the scene (backend state);
    // the console must render chips only for the turn the message belongs to.
    const out = extractTurnImageSuggestions({
      turn_id: "turn-9",
      image_suggestions: [olderTurnSuggestion, currentTurnSuggestion],
    });
    expect(out).toEqual([currentTurnSuggestion]);
  });

  it("returns nothing when the turn has no suggestions", () => {
    expect(extractTurnImageSuggestions({ turn_id: "turn-9", image_suggestions: [] })).toEqual([]);
    expect(extractTurnImageSuggestions({ turn_id: "turn-9" })).toEqual([]);
    expect(extractTurnImageSuggestions(undefined)).toEqual([]);
    expect(extractTurnImageSuggestions({})).toEqual([]);
  });

  it("drops malformed entries instead of throwing", () => {
    const out = extractTurnImageSuggestions({
      turn_id: "turn-9",
      image_suggestions: [
        "garbage",
        { suggestion_id: 42 },
        null,
        currentTurnSuggestion,
      ],
    });
    expect(out).toEqual([currentTurnSuggestion]);
  });

  it("keeps suggestions when metadata has no turn_id (defensive)", () => {
    // Older sessions persisted before turn_id existed: don't hide chips.
    const out = extractTurnImageSuggestions({ image_suggestions: [currentTurnSuggestion] });
    expect(out).toEqual([currentTurnSuggestion]);
  });
});
