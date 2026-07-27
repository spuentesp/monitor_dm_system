/**
 * Shared play-side constants — tones, mode labels, phase styles — used
 * by PlayConsole, SetupPanel, and any future play UI. Previously these
 * were duplicated verbatim across PlayConsole and SetupPanel.
 */

export const TONES = ["dramatic", "grim", "horror", "heroic", "mystery", "adventure"] as const;
export type Tone = (typeof TONES)[number];

export const TONE_DESCRIPTIONS: Record<Tone, string> = {
  dramatic: "Baroque, weighty, personal stakes",
  grim: "Terse, industrial, cosmic dread",
  horror: "Dread through omission, slow tension",
  heroic: "Elevated, mythic, earned hope",
  mystery: "Layered, rationed, careful",
  adventure: "Kinetic, immediate, punchy",
};

export const MODE_LABEL: Record<string, string> = {
  autonomous_gm: "Autonomous GM",
  gm_assistant: "GM Assistant",
  world_architect: "World Architect",
};

export const PHASE_STYLE: Record<string, { label: string; cls: string }> = {
  awaiting_character: { label: "Choosing character", cls: "text-amber-300 border-amber-500/30 bg-amber-500/10" },
  awaiting_premise: { label: "Setting premise", cls: "text-amber-300 border-amber-500/30 bg-amber-500/10" },
  setup: { label: "Setup", cls: "text-amber-300 border-amber-500/30 bg-amber-500/10" },
  active_play: { label: "In play", cls: "text-emerald-300 border-emerald-500/30 bg-emerald-500/10" },
  scene_ended: { label: "Scene ended", cls: "text-cyan-300 border-cyan-500/30 bg-cyan-500/10" },
};