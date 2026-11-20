import type { ImageSuggestionMeta } from "@/features/chat/types";

/**
 * Wrap an outgoing message in ((...)) for plain GM chat (no persona
 * selected) in OOC mode, so the explicit signal reaches the GM as the
 * same syntax it already recognizes (gm_awareness.py documents "((" as
 * an OOC marker) — mirrors the CLI's /ooc handling. When a persona
 * character is selected, chatMode routes through the separate
 * chat_mode='ooc' character-chat path via send options instead, so this
 * only applies when there's no selected character. Avoids double-wrapping
 * text the player already wrapped themselves.
 */
export function wrapOutgoingMessageForOoc(
  text: string,
  { chatMode, hasSelectedCharacter }: { chatMode: "ic" | "ooc"; hasSelectedCharacter: boolean },
): string {
  const trimmed = text.trim();
  if (hasSelectedCharacter || chatMode !== "ooc" || trimmed.startsWith("((")) {
    return text;
  }
  return `((${trimmed}))`;
}

/**
 * [P-19] Begin Story visibility gate. The story-agreements summary is always
 * the latest GM message while Session Zero awaits confirmation (any further
 * chat input re-presents it), so key on the latest GM metadata *type*.
 * The previous gate searched `recent_phase_sequence` — a list of metadata
 * *phase* values ("session_zero", …) — for the type string
 * "story_agreements_summary", which could never match, so the button never
 * rendered.
 */
export function shouldShowBeginStory(
  phase: string | undefined,
  latestGmMetadata: Record<string, unknown> | undefined,
): boolean {
  return phase === "session_zero" && latestGmMetadata?.type === "story_agreements_summary";
}

// ─── Image suggestions (Task 9) ────────────────────────────────────

const IMAGE_SUGGESTION_REASONS: ReadonlySet<string> = new Set([
  "location_change",
  "npc_entry",
  "visual_state_change",
  "climax",
]);

/**
 * Extract the current turn's image suggestions from a GM message's metadata.
 *
 * The backend accumulates `image_suggestions` over the scene (rate-limit
 * bookkeeping), so entries from earlier turns are filtered out via
 * `source_turn_id === metadata.turn_id` — chips always belong to the turn
 * that produced them. Malformed entries are dropped rather than thrown.
 */
export function extractTurnImageSuggestions(
  metadata: Record<string, unknown> | undefined,
): ImageSuggestionMeta[] {
  if (!metadata || !Array.isArray(metadata.image_suggestions)) return [];
  const turnId = typeof metadata.turn_id === "string" ? metadata.turn_id : null;
  return (metadata.image_suggestions as unknown[]).filter((s): s is ImageSuggestionMeta => {
    if (!s || typeof s !== "object") return false;
    const c = s as Partial<ImageSuggestionMeta>;
    if (typeof c.suggestion_id !== "string" || typeof c.source_turn_id !== "string") return false;
    if (typeof c.reason !== "string" || !IMAGE_SUGGESTION_REASONS.has(c.reason)) return false;
    return turnId === null || c.source_turn_id === turnId;
  });
}
