"use client";

import { Layers, ScrollText, ShieldCheck, Sparkles, X } from "lucide-react";

import type { ChatSessionState, PlaytestBenchmark, Session, StandaloneCharacter } from "@/lib/types";
import { workingStateChips } from "@/lib/workingState";
import { cn } from "@/lib/utils";

import { CastPanel } from "./CastPanel";
import { CharacterPanel } from "./CharacterPanel";
import { CombatPanel } from "./CombatPanel";
import { StoryPanel } from "./StoryPanel";
import { CanonReviewPanel } from "@/components/canon/CanonReviewPanel";

// ─── Types ───────────────────────────────────────────────────────────

export interface AuditMeta {
  intent_type?: string;
  success_level?: string;
  roll_breakdown?: string;
  effects?: string[];
  risk_preview?: string;
  consequence_options?: string[];
  requires_player_choice?: boolean;
  narrative_pressure?: string;
}

export interface SocialRead {
  stance_after?: string;
  reason?: string;
  confidence?: number;
  deltas?: Record<string, number>;
}

export interface PlaySidePanelProps {
  /** Drawer state — true renders as an overlay drawer (below xl). */
  open: boolean;
  onClose: () => void;
  activeSession: Session | null;
  sessionState: ChatSessionState | undefined;
  activeBenchmark: PlaytestBenchmark | null;
  auditMeta: AuditMeta;
  socialRead: SocialRead;
  relationshipSnapshot: Record<string, unknown>;
  socialDeltaEntries: [string, number][];
  recapLines: string[];
  castSpeaker: { id: string; name: string } | null;
  onSwitchSpeaker: (id: string, name: string) => void;
  selectedCharacter: StandaloneCharacter | null;
  onSelectCharacter: (id: string | null, character: StandaloneCharacter | null) => void;
  chatMode: "ic" | "ooc";
  onChatModeChange: (mode: "ic" | "ooc") => void;
}

// ─── Working-state HUD (T-067/T-078) ─────────────────────────────────

function WorkingStateCard({ state }: { state: Record<string, unknown> }) {
  const chips = workingStateChips(state);
  if (chips.length === 0) return null;
  return (
    <div className="glass rounded-2xl border border-white/5 p-4 space-y-3">
      <div className="flex items-center gap-2 text-slate-200">
        <ShieldCheck className="w-4 h-4 text-emerald-400" />
        <h2 className="text-sm font-semibold">Character State</h2>
      </div>
      <div className="flex flex-wrap gap-1.5">
        {chips.map((c, i) =>
          c.kind === "stat" ? (
            <span
              key={`${c.label}-${i}`}
              className="text-[11px] px-2 py-1 rounded-lg border border-emerald-500/20 bg-emerald-500/5 text-emerald-100 capitalize"
            >
              {c.label}
              {c.value ? ": " : ""}
              <span className="font-mono font-semibold text-emerald-300">{c.value}</span>
            </span>
          ) : (
            <span key={`${c.label}-${i}`} className="tag-amber text-[10px] capitalize">
              {c.label}
            </span>
          ),
        )}
      </div>
    </div>
  );
}

// ─── Side panel ──────────────────────────────────────────────────────

/**
 * Right-hand side panel of the play console: cast, character, working
 * state, story, canon review, session context, audit, social continuity and
 * benchmark notes.
 *
 * Below xl it renders as a collapsible overlay drawer (phone/tablet pass,
 * UX-6); at xl and up it is the static column it always was.
 */
export function PlaySidePanel({
  open,
  onClose,
  activeSession,
  sessionState,
  activeBenchmark,
  auditMeta,
  socialRead,
  relationshipSnapshot,
  socialDeltaEntries,
  recapLines,
  castSpeaker,
  onSwitchSpeaker,
  selectedCharacter,
  onSelectCharacter,
  chatMode,
  onChatModeChange,
}: PlaySidePanelProps) {
  return (
    <>
      {open && (
        <div
          className="fixed inset-0 z-30 bg-black/50 xl:hidden"
          onClick={onClose}
          aria-hidden="true"
        />
      )}
      <aside
        data-testid="play-side-panel"
        data-open={open}
        className={cn(
          "flex flex-col gap-4 p-4 overflow-y-auto",
          open
            ? "fixed inset-y-0 right-0 z-40 w-[min(88vw,360px)] bg-black/95 shadow-2xl xl:static xl:w-auto xl:shadow-none xl:bg-black/10"
            : "hidden bg-black/10 xl:flex",
        )}
      >
        {open && (
          <div className="flex items-center justify-between xl:hidden">
            <span className="text-xs font-semibold uppercase tracking-widest text-slate-500">
              Session panels
            </span>
            <button
              type="button"
              onClick={onClose}
              aria-label="Close side panels"
              className="flex h-8 w-8 items-center justify-center rounded-lg border border-white/10 text-slate-400 transition-colors hover:bg-white/5 hover:text-slate-200"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        )}

        {activeSession && (
          <CastPanel
            controlledCharacterIds={activeSession.controlled_character_ids ?? []}
            speakerCharacterId={activeSession.speaker_character_id ?? null}
            pendingSpeakerId={castSpeaker?.id ?? null}
            universeId={activeSession.universe_id ?? null}
            onSwitchSpeaker={onSwitchSpeaker}
          />
        )}

        <CharacterPanel
          selectedId={selectedCharacter?.id ?? null}
          onSelect={onSelectCharacter}
          chatMode={chatMode}
          onChatModeChange={onChatModeChange}
        />

        {sessionState?.latest_working_state &&
          Object.keys(sessionState.latest_working_state).length > 0 && (
            <>
              <WorkingStateCard state={sessionState.latest_working_state} />
              <CombatPanel state={sessionState.latest_working_state} />
            </>
          )}

        {activeSession?.story_id && (
          <div className="flex-shrink-0 h-[380px] border-t border-white/5 pt-4">
            <StoryPanel storyId={activeSession.story_id} />
          </div>
        )}

        {activeSession?.story_id && (
          <div className="flex-shrink-0 border-t border-white/5 pt-4">
            <CanonReviewPanel storyId={activeSession.story_id} compact />
          </div>
        )}

        <div className="glass rounded-2xl border border-white/5 p-4 space-y-3">
          <div className="flex items-center gap-2 text-slate-200">
            <Layers className="w-4 h-4 text-cyan-400" />
            <h2 className="text-sm font-semibold">Session Context</h2>
          </div>
          {activeSession ? (
            <div className="space-y-2 text-xs text-slate-400">
              <div><span className="text-slate-300">Setting:</span> {activeSession.multiverse_label ?? "Not set"}</div>
              <div><span className="text-slate-300">Universe:</span> {activeSession.universe_label ?? "Not set"}</div>
              <div><span className="text-slate-300">System:</span> {activeSession.system_label ?? "Not set"}</div>
              <div><span className="text-slate-300">Benchmark:</span> {activeSession.benchmark_label ?? "Custom free-play"}</div>
              <div><span className="text-slate-300">Speaker:</span> {activeSession.speaker_label ?? "You / current PC"}</div>
              {activeBenchmark?.comparison_group && <div><span className="text-slate-300">Comparison group:</span> {activeBenchmark.comparison_group}</div>}
              <div><span className="text-slate-300">Continuity:</span> changes persist in this universe across stories</div>
              <div><span className="text-slate-300">Story binding:</span> {activeSession.story_id ? "attached" : "not attached yet"}</div>
              <div><span className="text-slate-300">Scene binding:</span> {activeSession.scene_id ? "attached" : "not attached yet"}</div>
            </div>
          ) : (
            <p className="text-xs text-slate-500">Create a session to bind it to a setting, universe, and active speaker.</p>
          )}
        </div>

        <div className="glass rounded-2xl border border-white/5 p-4 space-y-3">
          <div className="flex items-center gap-2 text-slate-200">
            <Layers className="w-4 h-4 text-purple-400" />
            <h2 className="text-sm font-semibold">Audit & Resolution</h2>
          </div>
          {auditMeta.roll_breakdown ? (
            <div className="space-y-2 text-xs">
              {auditMeta.success_level && (
                <span className="tag-purple capitalize">{auditMeta.success_level.replace(/_/g, " ")}</span>
              )}
              <p className="text-slate-300">{auditMeta.roll_breakdown}</p>
              {auditMeta.intent_type && (
                <div className="text-slate-400 capitalize">
                  Intent: {auditMeta.intent_type.replace(/_/g, " ")}
                  {auditMeta.narrative_pressure ? ` · pressure ${auditMeta.narrative_pressure}` : ""}
                </div>
              )}
              {Array.isArray(auditMeta.effects) && auditMeta.effects.length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {auditMeta.effects.map((effect) => (
                    <span key={effect} className="tag-dim capitalize">
                      {effect.replace(/_/g, " ")}
                    </span>
                  ))}
                </div>
              )}
              {auditMeta.risk_preview && (
                <div className="rounded-xl border border-amber-500/20 bg-amber-500/5 px-3 py-2 text-amber-100">
                  <div className="font-medium text-amber-300">Risk & stakes</div>
                  <p className="mt-1 leading-relaxed">{auditMeta.risk_preview}</p>
                </div>
              )}
              {Array.isArray(auditMeta.consequence_options) && auditMeta.consequence_options.length > 0 && (
                <div className="rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-slate-200">
                  <div className="font-medium text-slate-100">
                    {auditMeta.requires_player_choice ? "Consequence choices" : "Likely next beats"}
                  </div>
                  <ul className="mt-1 space-y-1 list-disc pl-4 text-[11px] text-slate-300">
                    {auditMeta.consequence_options.slice(0, 3).map((option) => (
                      <li key={option}>{option}</li>
                    ))}
                  </ul>
                </div>
              )}
              <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/5 px-3 py-2 text-emerald-200">
                <div className="flex items-center gap-1.5 font-medium">
                  <ShieldCheck className="w-3.5 h-3.5" />
                  CanonKeeper
                </div>
                <p className="text-[11px] mt-1 text-emerald-100/85">
                  Pending scene-end review. Accepted changes in this universe will persist across future stories.
                </p>
              </div>
            </div>
          ) : (
            <p className="text-xs text-slate-500">
              No mechanical resolution yet. When MONITOR triggers a check, the latest roll breakdown and outcome will appear here.
            </p>
          )}
        </div>

        <div className="glass rounded-2xl border border-white/5 p-4 space-y-3">
          <div className="flex items-center gap-2 text-slate-200">
            <Sparkles className="w-4 h-4 text-cyan-400" />
            <h2 className="text-sm font-semibold">NPC Social Continuity</h2>
          </div>
          {socialRead.stance_after || Object.keys(relationshipSnapshot).length > 0 ? (
            <div className="space-y-2 text-xs text-slate-300">
              {socialRead.stance_after && (
                <div><span className="text-slate-400">Current stance:</span> {socialRead.stance_after}</div>
              )}
              {typeof relationshipSnapshot.trust === "number" && (
                <div><span className="text-slate-400">Trust:</span> {relationshipSnapshot.trust.toFixed(2)}</div>
              )}
              {typeof relationshipSnapshot.fear === "number" && (
                <div><span className="text-slate-400">Fear:</span> {relationshipSnapshot.fear.toFixed(2)}</div>
              )}
              {typeof relationshipSnapshot.leverage === "number" && (
                <div><span className="text-slate-400">Leverage:</span> {relationshipSnapshot.leverage.toFixed(2)}</div>
              )}
              {socialDeltaEntries.length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {socialDeltaEntries.map(([key, value]) => (
                    <span key={key} className="tag-dim">
                      {key} {value >= 0 ? "+" : ""}{value.toFixed(2)}
                    </span>
                  ))}
                </div>
              )}
              {socialRead.reason && (
                <p className="leading-relaxed text-slate-400">{socialRead.reason}</p>
              )}
              {sessionState?.recent_npc_stances && sessionState.recent_npc_stances.length > 1 && (
                <div>
                  <span className="text-slate-400">Recent stances:</span> {sessionState.recent_npc_stances.slice(-4).join(" → ")}
                </div>
              )}
            </div>
          ) : (
            <p className="text-xs text-slate-500">
              Social stance changes will appear here once an NPC scene produces durable relationship drift.
            </p>
          )}
        </div>

        <div className="glass rounded-2xl border border-white/5 p-4 space-y-3">
          <div className="flex items-center gap-2 text-slate-200">
            <ScrollText className="w-4 h-4 text-amber-400" />
            <h2 className="text-sm font-semibold">Benchmark Notes</h2>
          </div>
          {activeBenchmark ? (
            <div className="space-y-2 text-xs text-slate-400">
              <p className="leading-relaxed">{activeBenchmark.description}</p>
              {activeBenchmark.focus_areas.length > 0 && (
                <div>
                  <span className="text-slate-300">Focus:</span> {activeBenchmark.focus_areas.slice(0, 3).join(" · ")}
                </div>
              )}
              {activeBenchmark.expected_signals.length > 0 && (
                <div>
                  <span className="text-slate-300">Expected:</span> {activeBenchmark.expected_signals.slice(0, 2).join(" / ")}
                </div>
              )}
              {activeBenchmark.adversarial_goals.length > 0 && (
                <div>
                  <span className="text-slate-300">Probe for:</span> {activeBenchmark.adversarial_goals.slice(0, 2).join(" / ")}
                </div>
              )}
            </div>
          ) : recapLines.length > 0 ? (
            <div className="space-y-2 text-xs text-slate-400">
              {recapLines.map((line, index) => (
                <p key={`${line}-${index}`} className="leading-relaxed">{line}</p>
              ))}
            </div>
          ) : (
            <p className="text-xs text-slate-500">Scene recaps and recent turns will appear here for quick continuation.</p>
          )}
        </div>
      </aside>
    </>
  );
}
