// @vitest-environment happy-dom
import { describe, it, expect } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { usePlaySuggestions } from "./usePlaySuggestions";
import type { Message } from "@/lib/types";

function gm(over: Partial<Message> = {}): Message {
  return {
    id: "gm-1",
    session_id: "s-1",
    role: "gm",
    content: "The door creaks open.",
    timestamp: new Date().toISOString(),
    metadata: {},
    ...over,
  };
}

function player(over: Partial<Message> = {}): Message {
  return {
    id: "p-1",
    session_id: "s-1",
    role: "player",
    content: "I step inside.",
    timestamp: new Date().toISOString(),
    metadata: {},
    ...over,
  };
}

const SUGGESTION = {
  suggestion_id: "11111111-1111-4111-8111-111111111111",
  asset_type: "location",
  subject_entity_ids: ["22222222-2222-4222-8222-222222222222"],
  reason: "location_change",
  aspect_ratio: "16:9",
  source_turn_id: "turn-9",
};

describe("usePlaySuggestions", () => {
  it("always offers the static quick actions", () => {
    const { result } = renderHook(() =>
      usePlaySuggestions({ messages: [], sessionId: "s-1", suggestionsEnabled: true }),
    );
    const labels = result.current.quickActions.map((a) => a.label);
    expect(labels).toContain("Look around");
    expect(labels).toContain("Ask the Oracle");
    expect(labels).toContain("Story so far");
    expect(labels).not.toContain("Retry last");
  });

  it("adds Retry last once a player action exists", () => {
    const { result } = renderHook(() =>
      usePlaySuggestions({
        messages: [player(), gm()],
        sessionId: "s-1",
        suggestionsEnabled: true,
      }),
    );
    const retry = result.current.quickActions.find((a) => a.label === "Retry last");
    expect(retry).toBeDefined();
    expect(retry?.text).toBe("I step inside.");
    expect(retry?.disabled).toBe(false);
  });

  it("surfaces only this turn's image suggestions", () => {
    const { result } = renderHook(() =>
      usePlaySuggestions({
        messages: [
          gm({
            metadata: {
              turn_id: "turn-9",
              image_suggestions: [
                { ...SUGGESTION, suggestion_id: "old", source_turn_id: "turn-6" },
                SUGGESTION,
              ],
            },
          }),
        ],
        sessionId: "s-1",
        suggestionsEnabled: true,
      }),
    );
    expect(result.current.visibleImageSuggestions).toHaveLength(1);
    expect(result.current.visibleImageSuggestions[0].suggestion_id).toBe(SUGGESTION.suggestion_id);
  });

  it("hides image suggestions when generation settings disable them", () => {
    const { result } = renderHook(() =>
      usePlaySuggestions({
        messages: [gm({ metadata: { turn_id: "turn-9", image_suggestions: [SUGGESTION] } })],
        sessionId: "s-1",
        suggestionsEnabled: false,
      }),
    );
    expect(result.current.visibleImageSuggestions).toEqual([]);
  });

  it("settles (dismisses) a suggestion chip locally", () => {
    const { result } = renderHook(() =>
      usePlaySuggestions({
        messages: [gm({ metadata: { turn_id: "turn-9", image_suggestions: [SUGGESTION] } })],
        sessionId: "s-1",
        suggestionsEnabled: true,
      }),
    );
    expect(result.current.visibleImageSuggestions).toHaveLength(1);
    act(() => {
      result.current.settleImageSuggestion(SUGGESTION.suggestion_id);
    });
    expect(result.current.visibleImageSuggestions).toEqual([]);
  });

  it("builds guided-start chips from start_options metadata", () => {
    const { result } = renderHook(() =>
      usePlaySuggestions({
        messages: [
          gm({
            metadata: {
              type: "story_agreements_summary",
              start_options: [{ title: "The heist", summary: "Steal the crown" }],
            },
          }),
        ],
        sessionId: "s-1",
        suggestionsEnabled: true,
      }),
    );
    const chip = result.current.quickActions.find((a) => a.label === "The heist");
    expect(chip).toBeDefined();
    expect(chip?.onClick).toBe("fill");
  });
});
