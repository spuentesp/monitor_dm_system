"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import {
  Bot,
  BookOpen,
  ChevronDown,
  Eye,
  Flag,
  Layers,
  RotateCcw,
  ScrollText,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { chatApi } from "@/lib/api";
import { PLAY_KEYS } from "@/lib/query-keys";
import { useWorldContext } from "@/lib/world-context";
import { workingStateChips } from "@/lib/workingState";
import type { ChatSessionState, Message, PlaytestBenchmark, Session, StandaloneCharacter } from "@/lib/types";
import { cn } from "@/lib/utils";
import { TONES, TONE_DESCRIPTIONS, MODE_LABEL, PHASE_STYLE } from "@/lib/play-constants";

import {
  ChatList,
  Composer,
  ConsequenceBanner,
  useChatSession,
  type QuickAction,
} from "@/features/chat";

import { CharacterPanel } from "./CharacterPanel";
import { CombatPanel } from "./CombatPanel";
import { StoryPanel } from "./StoryPanel";
import { ChatModeToggle } from "./ChatModeToggle";
import { CanonReviewPanel } from "@/components/canon/CanonReviewPanel";
import { RecapModal } from "./RecapModal";
import { PlayMessageBubble } from "./PlayMessageBubble";
import { SessionList } from "./SessionList";
import { SetupPanel, type SetupPayload } from "./SetupPanel";

// ─── Tone / mode labels (Play-specific) ─────────────────────────────
// See lib/play-constants.ts — shared with SetupPanel.

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

// ─── Orchestrator ────────────────────────────────────────────────────

export default function PlayConsole() {
  const qc = useQueryClient();
  const searchParams = useSearchParams();
  const world = useWorldContext();

  const requestedSessionId = searchParams.get("session");
  const urlUniverseId = searchParams.get("universe");
  // URL params win; the persisted global world context is the default (T-077)
  const requestedUniverseId = urlUniverseId ?? world.universeId;
  const requestedMultiverseId = searchParams.get("multiverse") ?? world.multiverseId;

  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  // Deep link from Worlds tree ("Play here"): open setup with the universe
  // preselected. Only an explicit URL param auto-opens setup — the persisted
  // world default must not hijack normal "resume last session" visits.
  const [showSetup, setShowSetup] = useState(() => Boolean(urlUniverseId && !requestedSessionId));
  const [selectedCharacter, setSelectedCharacter] = useState<StandaloneCharacter | null>(null);
  const [chatMode, setChatMode] = useState<"ic" | "ooc">("ic");
  const [showRecap, setShowRecap] = useState(false);
  const [endingScene, setEndingScene] = useState(false);

  // ─── Sessions ─────────────────────────────────────────────────────
  const { data: sessions = [], isLoading: sessionsLoading } = useQuery({
    queryKey: PLAY_KEYS.sessions,
    queryFn: () => chatApi.listSessions().then((s) => s.filter((x) => x.mode !== "world_architect")),
  });

  const { data: benchmarkCatalog = [] } = useQuery<PlaytestBenchmark[]>({
    queryKey: PLAY_KEYS.benchmarks,
    queryFn: chatApi.listBenchmarks,
  });

  useEffect(() => {
    if (
      requestedSessionId &&
      sessions.some((session) => session.id === requestedSessionId) &&
      activeSessionId !== requestedSessionId
    ) {
      setActiveSessionId(requestedSessionId);
      setShowSetup(false);
      return;
    }
    if (!activeSessionId && sessions[0]?.id) {
      setActiveSessionId(sessions[0].id);
    }
  }, [sessions, activeSessionId, requestedSessionId]);

  // ─── Chat session (the streaming state machine) ──────────────────
  const onTurnSettled = useCallback(() => {
    qc.invalidateQueries({ queryKey: PLAY_KEYS.sessions });
  }, [qc]);

  const chat = useChatSession({
    sessionId: activeSessionId,
    onTurnSettled,
  });

  const { data: sessionState } = useQuery<ChatSessionState>({
    queryKey: PLAY_KEYS.state(activeSessionId),
    queryFn: () => chatApi.getSessionState(activeSessionId!),
    enabled: !!activeSessionId,
  });

  // ─── Composer local state ────────────────────────────────────────
  const [inputValue, setInputValue] = useState("");

  // ─── Mutations ───────────────────────────────────────────────────
  const createSession = useMutation({
    mutationFn: chatApi.createSession,
    onSuccess: (session) => {
      qc.invalidateQueries({ queryKey: PLAY_KEYS.sessions });
      setActiveSessionId(session.id);
      setShowSetup(false);
      if (session.universe_id) {
        world.setWorld({
          multiverseId: session.multiverse_id ?? null,
          universeId: session.universe_id,
          universeLabel: session.universe_label ?? null,
        });
      }
    },
  });

  const deleteSession = useMutation({
    mutationFn: chatApi.deleteSession,
    onSuccess: (_data, sessionId) => {
      qc.invalidateQueries({ queryKey: PLAY_KEYS.sessions });
      if (activeSessionId === sessionId) {
        // Tear down any state that referenced the about-to-be-gone session.
        // The chat hook clears itself when activeSessionId becomes null
        // (see useChatSession's sessionId-change effect).
        qc.removeQueries({ queryKey: PLAY_KEYS.messages(sessionId) });
        qc.removeQueries({ queryKey: PLAY_KEYS.state(sessionId) });
        setActiveSessionId(null);
      }
    },
  });

  const patchTone = useMutation({
    mutationFn: ({ tone }: { tone: string }) =>
      chatApi.patchSession(activeSessionId!, { tone }),
    onSuccess: () => qc.invalidateQueries({ queryKey: PLAY_KEYS.sessions }),
  });

  const renameSession = useMutation({
    mutationFn: ({ id, title }: { id: string; title: string }) =>
      chatApi.patchSession(id, { title }),
    onSuccess: () => qc.invalidateQueries({ queryKey: PLAY_KEYS.sessions }),
  });

  const handleEndScene = () => {
    if (!activeSessionId || endingScene) return;
    setEndingScene(true);
    chatApi
      .endScene(activeSessionId)
      .then(() => {
        qc.invalidateQueries({ queryKey: PLAY_KEYS.messages(activeSessionId) });
        qc.invalidateQueries({ queryKey: PLAY_KEYS.state(activeSessionId) });
        qc.invalidateQueries({ queryKey: PLAY_KEYS.sessions });
      })
      .catch((err: unknown) => {
        const detail = err instanceof Error ? err.message : "End-scene failed";
        chat.surfaceFailure(`Scene wrap-up failed: ${detail}`);
      })
      .finally(() => setEndingScene(false));
  };

  // ─── Composer send options ──────────────────────────────────────
  const sendOptions = useMemo(() => {
    const opts: { chat_mode?: "ic" | "ooc"; character_id?: string; is_ooc_persona?: boolean } = {};
    if (selectedCharacter) {
      opts.character_id = selectedCharacter.id;
      if (chatMode === "ooc" || selectedCharacter.is_ooc_persona) {
        opts.chat_mode = "ooc";
        opts.is_ooc_persona = selectedCharacter.is_ooc_persona;
      }
    }
    return opts;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedCharacter, chatMode]);

  const handleComposerSubmit = (text: string) => {
    chat.send(text, sendOptions);
  };

  // ─── Derived UI bits ────────────────────────────────────────────
  const activeSession = sessions.find((s) => s.id === activeSessionId) ?? null;
  const activeBenchmark = benchmarkCatalog.find((b) => b.benchmark_id === activeSession?.benchmark_id) ?? null;

  const latestAudit = useMemo(() => {
    return [...chat.messages]
      .reverse()
      .find((msg) => msg.role === "gm" && Object.keys(msg.metadata ?? {}).length > 0);
  }, [chat.messages]);

  const recapLines = useMemo(() => {
    return chat.messages
      .slice(-4)
      .map((msg) => `${msg.role === "gm" ? "MONITOR" : msg.role === "player" ? "You" : "System"}: ${msg.content}`)
      .slice(-3);
  }, [chat.messages]);

  const auditMeta = (latestAudit?.metadata ?? {}) as {
    intent_type?: string;
    success_level?: string;
    roll_breakdown?: string;
    effects?: string[];
    risk_preview?: string;
    consequence_options?: string[];
    requires_player_choice?: boolean;
    narrative_pressure?: string;
  };

  const socialRead = (sessionState?.latest_social_read ?? {}) as {
    stance_after?: string;
    reason?: string;
    confidence?: number;
    deltas?: Record<string, number>;
  };
  const relationshipSnapshot = (sessionState?.latest_relationship_snapshot ?? {}) as Record<string, unknown>;
  const socialDeltaEntries = Object.entries(socialRead.deltas ?? {}).slice(0, 4);

  const quickActions = useMemo<QuickAction[]>(() => [
    {
      label: "Look around",
      icon: Eye,
      onClick: "submit",
      text: "I pause and take in my surroundings — what do I see, hear, and notice?",
    },
    {
      label: "Ask the Oracle",
      icon: Sparkles,
      onClick: "fill",
      text: "(( Oracle: ",
      className: "hover:border-purple-500/30 hover:bg-purple-500/10",
      title: "Ask the oracle a yes/no question about the world",
    },
    {
      label: "Story so far",
      icon: BookOpen,
      onClick: "fill",
      text: "/recap",
      className: "hover:border-amber-500/30 hover:bg-amber-500/10",
    },
    ...(chat.messages.some((m) => m.role === "player")
      ? [
          {
            label: "Retry last",
            icon: RotateCcw,
            onClick: "submit" as const,
            text: chat.messages
              .slice()
              .reverse()
              .find(
                (m) =>
                  m.role === "player" &&
                  (m.metadata as { type?: string })?.type !== "dice_result",
              )?.content ?? "",
            className: "hover:border-cyan-500/30 hover:bg-cyan-500/10",
            title: "Re-send your previous action",
            disabled: !chat.messages
              .slice()
              .reverse()
              .some(
                (m) =>
                  m.role === "player" &&
                  (m.metadata as { type?: string })?.type !== "dice_result",
              ),
          },
        ]
      : []),
  ], [chat.messages]);

  const pendingConsequence = sessionState?.pending_consequence;
  const hasConsequence =
    pendingConsequence &&
    typeof pendingConsequence === "object" &&
    Object.keys(pendingConsequence).length > 0 &&
    Array.isArray((pendingConsequence as { options?: unknown }).options) &&
    ((pendingConsequence as { options: unknown[] }).options ?? []).length > 0;

  // ─── Render ─────────────────────────────────────────────────────
  const renderBubble = useCallback(
    (msg: (typeof chat.messages)[number]) => <PlayMessageBubble msg={msg} />,
    [],
  );

  return (
    <div className="flex h-full min-h-0">
      <SessionList
        sessions={sessions}
        activeId={activeSessionId}
        onSelect={setActiveSessionId}
        onNew={() => setShowSetup(true)}
        onDelete={(id) => deleteSession.mutate(id)}
        onRename={(id, title) => renameSession.mutate({ id, title })}
        loading={sessionsLoading}
      />

      <div className="flex-1 min-w-0 grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_340px]">
        <div className="flex flex-col min-w-0 border-r border-white/5">
          <div className="flex items-center justify-between px-6 py-3.5 border-b border-white/5 glass">
            <div>
              <p className="section-label">P-18 Play Console</p>
              <h1 className="text-sm font-semibold text-slate-200 mt-1">
                {activeSession?.title ?? "Select or create a session"}
              </h1>
              {activeSession && (
                <p className="text-xs text-slate-600 mt-0.5">
                  {(MODE_LABEL[activeSession.mode] ?? activeSession.mode)} · {chat.messages.length} messages
                </p>
              )}
            </div>
            <div className="flex items-center gap-2">
              {activeSession?.tone && (
                <div className="relative group">
                  <button aria-label="Change session tone" className="tag-purple capitalize flex items-center gap-1 cursor-pointer hover:bg-purple-500/20 transition-colors">
                    {activeSession.tone}
                    <ChevronDown className="w-2.5 h-2.5 opacity-60" />
                  </button>
                  <div className="absolute right-0 top-full mt-1 z-50 hidden group-hover:block glass rounded-xl border border-white/10 p-2 space-y-0.5 min-w-[180px]">
                    {TONES.map((t) => (
                      <button
                        key={t}
                        onClick={() => patchTone.mutate({ tone: t })}
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
              {activeSession && (
                <span className="tag-cyan capitalize">
                  {MODE_LABEL[activeSession.mode] ?? activeSession.mode}
                </span>
              )}
              {activeSession && (
                <PhaseChip phase={sessionState?.session?.phase ?? activeSession.phase} />
              )}
              {selectedCharacter && (
                <ChatModeToggle mode={chatMode} onChange={setChatMode} />
              )}
              {activeSessionId && (
                <button
                  onClick={handleEndScene}
                  disabled={endingScene}
                  className="ml-auto flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs border border-amber-500/30 text-amber-300 hover:bg-amber-500/10 disabled:opacity-50 transition-all"
                  title="Complete the current scene and advance the story"
                >
                  <Flag className="w-3 h-3" />
                  {endingScene ? "Ending…" : "End scene"}
                </button>
              )}
            </div>
          </div>

          {!activeSessionId && !showSetup && (
            <div className="flex-1 flex flex-col items-center justify-center text-center space-y-4">
              <div className="w-16 h-16 rounded-2xl bg-cyan-500/10 border border-cyan-500/20 flex items-center justify-center shadow-cyan-glow">
                <Bot className="w-8 h-8 text-cyan-400" />
              </div>
              <div>
                <h2 className="text-lg font-semibold text-slate-200">MONITOR Play</h2>
                <p className="text-sm text-slate-600 mt-1 max-w-md">
                  Start a session, choose a setting and universe, then tell MONITOR what kind of story or opening scene you want in chat.
                </p>
              </div>
              <button onClick={() => setShowSetup(true)} className="btn-cyber">
                <Sparkles className="w-4 h-4" />
                New Play Session
              </button>
            </div>
          )}

          {showSetup && (
            <div className="flex-1 overflow-y-auto px-6 py-4">
              <SetupPanel
                isPending={createSession.isPending}
                initialMultiverseId={requestedMultiverseId}
                initialUniverseId={requestedUniverseId}
                onCreate={(payload: SetupPayload) => createSession.mutate(payload)}
              />
            </div>
          )}

          {!showSetup && activeSessionId && (
            <>
              <ChatList
                messages={chat.messages}
                streamingMsg={chat.streamingMsg}
                isTyping={chat.isTyping}
                sendFailure={chat.sendFailure}
                pendingDiceRequest={chat.pendingDiceRequest}
                renderBubble={renderBubble}
                onDiceResult={chat.submitDiceResult}
                onRetry={chat.retry}
                onDismissFailure={chat.dismissFailure}
              />

              <div className="px-6 pb-2">
                {hasConsequence && (
                  <ConsequenceBanner
                    pending={{
                      options: ((pendingConsequence as { options?: string[] }).options ?? []) as string[],
                      risk_preview: (pendingConsequence as { risk_preview?: string }).risk_preview,
                    }}
                    disabled={chat.isTyping || !!chat.streamingMsg}
                    onChoose={(opt) => chat.send(opt, sendOptions)}
                  />
                )}
              </div>

              <Composer
                value={inputValue}
                onChange={setInputValue}
                onSubmit={handleComposerSubmit}
                status={chat.status}
                isTyping={chat.isTyping}
                disabled={!activeSessionId}
                placeholder="Use *action* for in-fiction moves, or ((...)) for OOC / rules questions…"
                quickActions={quickActions}
                extraTop={
                  activeBenchmark?.starter_questions &&
                  activeBenchmark.starter_questions.length > 0 ? (
                    <div className="mb-3">
                      <p className="text-[10px] text-amber-400 uppercase tracking-wider mb-2">
                        Benchmark probes
                      </p>
                      <div className="flex flex-wrap gap-2">
                        {activeBenchmark.starter_questions.slice(0, 3).map((question) => (
                          <button
                            key={question}
                            onClick={() => setInputValue(question)}
                            className="px-2.5 py-1 rounded-full text-[11px] border border-amber-500/20 text-amber-200 hover:bg-amber-500/10 transition-all"
                          >
                            {question}
                          </button>
                        ))}
                      </div>
                    </div>
                  ) : null
                }
              />
            </>
          )}
        </div>

        <aside className="hidden xl:flex xl:flex-col gap-4 p-4 overflow-y-auto bg-black/10">
          <CharacterPanel
            selectedId={selectedCharacter?.id ?? null}
            onSelect={(id, char) => setSelectedCharacter(char)}
            chatMode={chatMode}
            onChatModeChange={setChatMode}
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
      </div>

      {showRecap && activeSessionId && (
        <RecapModal sessionId={activeSessionId} onClose={() => setShowRecap(false)} />
      )}
    </div>
  );
}