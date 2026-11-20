"use client";

import { ChevronDown, Dices, Flag, List, PanelRight } from "lucide-react";

import type { ChatSessionState, Session } from "@/lib/types";
import { cn } from "@/lib/utils";

import { ChatModeToggle } from "./ChatModeToggle";
import { CanonPendingBadge } from "./CanonPendingBadge";
import { shouldShowBeginStory } from "./playConsoleHelpers";

// ─── Tone / mode labels (Play-specific) ─────────────────────────────

const TONES = ["dramatic", "grim", "horror", "heroic", "mystery", "adventure"] as const;
type Tone = (typeof TONES)[number];

const ROLL_MODELS = ["tap", "manual", "gm"] as const;
type RollModel = (typeof ROLL_MODELS)[number];
const ROLL_MODEL_LABEL: Record<RollModel, string> = {
  tap: "Tap to roll",
  manual: "Roll my own",
  gm: "GM rolls",
};
const ROLL_MODEL_DESC: Record<RollModel, string> = {
  tap: "Tap the die — the server rolls (fair & authoritative)",
  manual: "Enter your own physical/virtual roll",
  gm: "The GM rolls for you and weaves the result",
};

const TONE_DESCRIPTIONS: Record<Tone, string> = {
  dramatic: "Baroque, weighty, personal stakes",
  grim: "Terse, industrial, cosmic dread",
  horror: "Dread through omission, slow tension",
  heroic: "Elevated, mythic, earned hope",
  mystery: "Layered, rationed, careful",
  adventure: "Kinetic, immediate, punchy",
};

const MODE_LABEL: Record<string, string> = {
  autonomous_gm: "Autonomous GM",
  gm_assistant: "GM Assistant",
  world_architect: "World Architect",
};

const PHASE_STYLE: Record<string, { label: string; cls: string }> = {
  awaiting_character: { label: "Choosing character", cls: "text-amber-300 border-amber-500/30 bg-amber-500/10" },
  awaiting_premise: { label: "Setting premise", cls: "text-amber-300 border-amber-500/30 bg-amber-500/10" },
  setup: { label: "Setup", cls: "text-amber-300 border-amber-500/30 bg-amber-500/10" },
  active_play: { label: "In play", cls: "text-emerald-300 border-emerald-500/30 bg-emerald-500/10" },
  scene_ended: { label: "Scene ended", cls: "text-cyan-300 border-cyan-500/30 bg-cyan-500/10" },
};

// ─── Phase chip ──────────────────────────────────────────────────────

function PhaseChip({ phase }: { phase?: string }) {
  if (!phase) return null;
  const cfg = PHASE_STYLE[phase] ?? {
    label: phase.replace(/_/g, " "),
    cls: "text-slate-400 border-white/10 bg-white/5",
  };
  return (
    <span className={cn("text-[10px] px-2 py-0.5 rounded-full border capitalize", cfg.cls)}>
      {cfg.label}
    </span>
  );
}

// ─── Header ──────────────────────────────────────────────────────────

export interface PlayHeaderProps {
  activeSessionId: string | null;
  activeSession: Session | null;
  sessionState: ChatSessionState | undefined;
  messageCount: number;
  chatMode: "ic" | "ooc";
  onChatModeChange: (mode: "ic" | "ooc") => void;
  hasSelectedCharacter: boolean;
  onPatchTone: (tone: string) => void;
  onPatchRollModel: (rollModel: string) => void;
  onSkipPreplay: () => void;
  skipPending: boolean;
  onBeginStory: () => void;
  beginPending: boolean;
  endingScene: boolean;
  onEndScene: () => void;
  /** Toggle the sessions drawer (below md). */
  onToggleSessions: () => void;
  sessionsOpen: boolean;
  /** Toggle the side-panels drawer (below xl). */
  onTogglePanels: () => void;
  panelsOpen: boolean;
}

/** Session header bar: title, tone/roll-model menus, phase chips, drawer toggles. */
export function PlayHeader({
  activeSessionId,
  activeSession,
  sessionState,
  messageCount,
  chatMode,
  onChatModeChange,
  hasSelectedCharacter,
  onPatchTone,
  onPatchRollModel,
  onSkipPreplay,
  skipPending,
  onBeginStory,
  beginPending,
  endingScene,
  onEndScene,
  onToggleSessions,
  sessionsOpen,
  onTogglePanels,
  panelsOpen,
}: PlayHeaderProps) {
  const phase = sessionState?.session?.phase ?? activeSession?.phase;
  // Pre-play phases where the Skip-to-play affordance is meaningful.
  // A character must already be bound (either selected on setup or produced
  // by the character stage) before the Skip button accepts the click.
  const preplayPhases = [
    "awaiting_character",
    "character_interview",
    "char_creation",
    "session_zero",
  ];

  return (
    <div className="flex flex-wrap items-center justify-between gap-2 border-b border-white/5 px-3 py-3.5 glass sm:px-6">
      <div className="min-w-0">
        <p className="section-label">P-18 Play Console</p>
        <h1 className="mt-1 truncate text-sm font-semibold text-slate-200">
          {activeSession?.title ?? "Select or create a session"}
        </h1>
        {activeSession && (
          <p className="mt-0.5 text-xs text-slate-600">
            {(MODE_LABEL[activeSession.mode] ?? activeSession.mode)} · {messageCount} messages
          </p>
        )}
      </div>
      <div className="flex max-w-full flex-wrap items-center justify-end gap-2 shrink-0 sm:max-w-[60%]">
        {/* Phone-width drawers: sessions list (below md) and side panels (below xl). */}
        <button
          type="button"
          onClick={onToggleSessions}
          aria-label={sessionsOpen ? "Hide sessions" : "Show sessions"}
          aria-expanded={sessionsOpen}
          className="flex h-8 w-8 items-center justify-center rounded-lg border border-white/10 text-slate-400 transition-colors hover:bg-white/5 hover:text-slate-200 md:hidden"
          title="Sessions"
        >
          <List className="h-4 w-4" />
        </button>
        <button
          type="button"
          onClick={onTogglePanels}
          aria-label={panelsOpen ? "Hide side panels" : "Show side panels"}
          aria-expanded={panelsOpen}
          className="flex h-8 w-8 items-center justify-center rounded-lg border border-white/10 text-slate-400 transition-colors hover:bg-white/5 hover:text-slate-200 xl:hidden"
          title="Side panels"
        >
          <PanelRight className="h-4 w-4" />
        </button>
        {activeSession?.tone && (
          <div className="relative group">
            <button
              aria-label="Change session tone"
              className="tag-purple capitalize flex items-center gap-1 cursor-pointer hover:bg-purple-500/20 transition-colors whitespace-nowrap"
            >
              {activeSession.tone}
              <ChevronDown className="w-2.5 h-2.5 opacity-60" />
            </button>
            <div className="absolute right-0 top-full mt-1 z-50 hidden group-hover:block glass rounded-xl border border-white/10 p-2 space-y-0.5 min-w-[180px]">
              {TONES.map((t) => (
                <button
                  key={t}
                  onClick={() => onPatchTone(t)}
                  className={cn(
                    "w-full text-left px-3 py-1.5 rounded-lg text-xs capitalize transition-all",
                    t === activeSession.tone
                      ? "bg-purple-500/15 text-purple-300"
                      : "text-slate-400 hover:bg-white/5 hover:text-slate-200",
                  )}
                >
                  {t}
                  <span className="block text-[10px] text-slate-600 truncate">{TONE_DESCRIPTIONS[t]}</span>
                </button>
              ))}
            </div>
          </div>
        )}
        {activeSession && activeSession.play_mode !== "narrative" && (
          <div className="relative group">
            <button
              aria-label="Change dice roll model"
              className="flex items-center gap-1 cursor-pointer rounded-md px-2 py-0.5 text-xs bg-amber-500/10 text-amber-300 border border-amber-500/30 hover:bg-amber-500/20 transition-colors whitespace-nowrap"
            >
              <Dices className="w-3 h-3 opacity-70" />
              {ROLL_MODEL_LABEL[(activeSession.roll_model ?? "tap") as RollModel]}
              <ChevronDown className="w-2.5 h-2.5 opacity-60" />
            </button>
            <div className="absolute right-0 top-full mt-1 z-50 hidden group-hover:block glass rounded-xl border border-white/10 p-2 space-y-0.5 min-w-[220px]">
              {ROLL_MODELS.map((rm) => (
                <button
                  key={rm}
                  onClick={() => onPatchRollModel(rm)}
                  className={cn(
                    "w-full text-left px-3 py-1.5 rounded-lg text-xs transition-all",
                    rm === (activeSession.roll_model ?? "tap")
                      ? "bg-amber-500/15 text-amber-300"
                      : "text-slate-400 hover:bg-white/5 hover:text-slate-200",
                  )}
                >
                  {ROLL_MODEL_LABEL[rm]}
                  <span className="block text-[10px] text-slate-600 truncate">{ROLL_MODEL_DESC[rm]}</span>
                </button>
              ))}
            </div>
          </div>
        )}
        {activeSession && (
          <span className="tag-cyan capitalize whitespace-nowrap">
            {MODE_LABEL[activeSession.mode] ?? activeSession.mode}
          </span>
        )}
        {activeSession && <PhaseChip phase={phase} />}
        <CanonPendingBadge storyId={activeSession?.story_id ?? null} />
        {/* [G-1](c) Skip-to-play ghost button — visible only during
            pre-play phases; clears both Session Zero and character
            creation caches server-side. */}
        {activeSessionId &&
          preplayPhases.includes(phase ?? "") && (
            <button
              type="button"
              onClick={onSkipPreplay}
              disabled={skipPending}
              className="ml-1 text-[10px] px-2 py-0.5 rounded-full border border-cyan-500/30 bg-cyan-500/10 text-cyan-200 hover:bg-cyan-500/20 disabled:opacity-50 disabled:cursor-not-allowed transition whitespace-nowrap"
              title="Skip the pre-play interview and start playing"
            >
              {skipPending ? "Skipping…" : "Use defaults & begin"}
            </button>
          )}
        {/* [P-19] Begin Story — appear once Session Zero is awaiting
            confirmation. Hides once the session is finalized. */}
        {activeSessionId &&
          shouldShowBeginStory(phase, sessionState?.latest_gm_metadata) && (
            <button
              type="button"
              onClick={onBeginStory}
              disabled={beginPending}
              className="ml-1 text-[10px] px-2 py-0.5 rounded-full border border-emerald-500/30 bg-emerald-500/10 text-emerald-200 hover:bg-emerald-500/20 disabled:opacity-50 disabled:cursor-not-allowed transition whitespace-nowrap"
              title="Confirm the Session Zero agreements and start the story"
            >
              {beginPending ? "Beginning…" : "Begin Story"}
            </button>
          )}
        {hasSelectedCharacter && <ChatModeToggle mode={chatMode} onChange={onChatModeChange} />}
        {activeSessionId && (
          <button
            onClick={onEndScene}
            disabled={endingScene}
            className="ml-auto flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold border border-amber-500/50 bg-amber-500/15 text-amber-200 hover:bg-amber-500/25 hover:shadow-amber-glow disabled:opacity-50 transition-all whitespace-nowrap"
            title="Complete the current scene and advance the story"
          >
            <Flag className="w-3 h-3" />
            {endingScene ? "Ending…" : "End scene"}
          </button>
        )}
      </div>
    </div>
  );
}
