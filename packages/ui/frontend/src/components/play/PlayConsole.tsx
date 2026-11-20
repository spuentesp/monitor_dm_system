"use client";

import { useCallback, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Bot, Sparkles } from "lucide-react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { chatApi, imageApi } from "@/lib/api";
import { PLAY_KEYS } from "@/lib/query-keys";
import { useWorldContext } from "@/lib/world-context";
import type { StandaloneCharacter } from "@/lib/types";
import { useNotify } from "@/components/NotificationProvider";

import {
  ChatList,
  Composer,
  ConsequenceBanner,
} from "@/features/chat";
import { ImageSuggestionChip } from "@/components/visual/ImageSuggestionChip";

import { SessionList } from "./SessionList";
import { SetupPanel, type SetupPayload } from "./SetupPanel";
import { PlayHeader } from "./PlayHeader";
import { PlaySidePanel, type AuditMeta, type SocialRead } from "./PlaySidePanel";
import { ConnectionBanner } from "./ConnectionBanner";
import { TurnWaitBar } from "./TurnWaitBar";
import { TurnControls } from "./TurnControls";
import { RecapModal } from "./RecapModal";
import { PlayMessageBubble } from "./PlayMessageBubble";
import { usePlaySession } from "./hooks/usePlaySession";
import { usePlaySocket } from "./hooks/usePlaySocket";
import { usePlaySuggestions } from "./hooks/usePlaySuggestions";
import { buildQuickStartPayload } from "./quickStart";
import { friendlyTurnFailure, quotaMessageFor } from "./quota";
import { wrapOutgoingMessageForOoc } from "./playConsoleHelpers";

// Re-exported so existing imports/tests keep working after the UX-6 split.
export {
  wrapOutgoingMessageForOoc,
  shouldShowBeginStory,
  extractTurnImageSuggestions,
} from "./playConsoleHelpers";

/**
 * Orchestrator for the play console (P-18/P-19).
 *
 * UX-6 split: session state lives in hooks/usePlaySession, the streaming
 * socket + waiting state in hooks/usePlaySocket, chip derivation in
 * hooks/usePlaySuggestions, and the header / side panel are presentational
 * components. This component wires them together and owns the small pieces
 * of UI state (setup visibility, composer input, drawers, end-scene).
 */
export default function PlayConsole() {
  const qc = useQueryClient();
  const searchParams = useSearchParams();
  const world = useWorldContext();
  const { notify } = useNotify();

  const requestedSessionId = searchParams.get("session");
  const urlUniverseId = searchParams.get("universe");
  // URL params win; the persisted global world context is the default (T-077)
  const requestedUniverseId = urlUniverseId ?? world.universeId;
  const requestedMultiverseId = searchParams.get("multiverse") ?? world.multiverseId;

  const [showSetup, setShowSetup] = useState(() => Boolean(urlUniverseId && !requestedSessionId));
  const [selectedCharacter, setSelectedCharacter] = useState<StandaloneCharacter | null>(null);
  // Phase 4 (Task 5) / join Task 7: speaker picked in the cast panel. The
  // switch is applied IMMEDIATELY — PATCH /chat/{id} with
  // SessionPatch.speaker_character_id (ownership-checked server-side; the
  // backend invalidates the cached SceneLoop so the very next turn runs as
  // the new actor). castSpeaker is the optimistic local marker until the
  // session refetch confirms it; the next sent message still carries it as
  // IC character_id as a belt-and-braces seam.
  const [castSpeaker, setCastSpeaker] = useState<{ id: string; name: string } | null>(null);
  const [chatMode, setChatMode] = useState<"ic" | "ooc">("ic");
  const [showRecap, setShowRecap] = useState(false);
  const [endingScene, setEndingScene] = useState(false);
  // Phone-width drawers (UX-6): sessions below md, side panels below xl.
  const [showSessions, setShowSessions] = useState(false);
  const [showPanels, setShowPanels] = useState(false);

  // ─── Session state machine ────────────────────────────────────────
  const {
    sessions,
    sessionsLoading,
    activeSessionId,
    setActiveSessionId,
    activeSession,
    sessionState,
    benchmarkCatalog,
    createSession,
    deleteSession,
    renameSession,
    patchTone,
    patchRollModel,
    switchSpeaker,
    skipPreplay,
    beginStory,
  } = usePlaySession({
    requestedSessionId,
    onDeepLinkSelected: () => setShowSetup(false),
    onSessionCreated: () => setShowSetup(false),
  });

  // ─── Chat session (the streaming state machine) ──────────────────
  const { chat, status: socketStatus, turnActive, isWaitingForGm, waitedSeconds, cancelTurn } =
    usePlaySocket({ sessionId: activeSessionId });

  // Image-generation settings (Task 10): gates the suggestion chips and
  // pulled independently of the page so the chip visibility reacts to
  // SETTINGS_KEYS-style flips. Default true on first paint — the same
  // default the backend / Settings UI ships with.
  const { data: imageSettings } = useQuery({
    queryKey: ["image-generation-settings"],
    queryFn: imageApi.getImageGenerationSettings,
    staleTime: 5 * 60 * 1000,
  });
  const suggestionsEnabled = imageSettings?.image_suggestions_enabled ?? true;

  const { quickActions, visibleImageSuggestions, settleImageSuggestion } = usePlaySuggestions({
    messages: chat.messages,
    sessionId: activeSessionId,
    suggestionsEnabled,
  });

  // ─── Composer local state ────────────────────────────────────────
  const [inputValue, setInputValue] = useState("");

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
        const quota = quotaMessageFor(err);
        if (quota) {
          chat.surfaceFailure(quota);
          return;
        }
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
    // A cast-panel speaker pick wins for IC sends: the send endpoint turns an
    // IC character_id into the session speaker (Phase 4 Task 5).
    if (castSpeaker && opts.chat_mode !== "ooc") {
      opts.character_id = castSpeaker.id;
    }
    return opts;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedCharacter, chatMode, castSpeaker]);

  const handleComposerSubmit = (text: string) => {
    const wrapped = wrapOutgoingMessageForOoc(text, {
      chatMode,
      hasSelectedCharacter: !!selectedCharacter,
    });
    chat.send(wrapped, sendOptions);
  };

  // Regenerate: re-send the last player action through the existing
  // POST /chat/{id}/send endpoint so the GM produces a fresh reply (there is
  // no dedicated regenerate endpoint).
  const handleRegenerate = useCallback(
    (text: string) => {
      chat.send(text, sendOptions);
    },
    [chat, sendOptions],
  );

  // One-click Quick start (UX-6 onboarding): defaults → create → activate.
  const handleQuickStart = useCallback(async () => {
    try {
      const payload = await buildQuickStartPayload();
      await createSession.mutateAsync(payload);
    } catch (err) {
      const quota = quotaMessageFor(err);
      notify(
        "error",
        quota ?? `Couldn't start a session: ${err instanceof Error ? err.message : String(err)}`,
      );
    }
  }, [createSession, notify]);

  // ─── Derived UI bits ────────────────────────────────────────────
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

  const auditMeta = (latestAudit?.metadata ?? {}) as AuditMeta;

  const socialRead = (sessionState?.latest_social_read ?? {}) as SocialRead;
  const relationshipSnapshot = (sessionState?.latest_relationship_snapshot ?? {}) as Record<string, unknown>;
  const socialDeltaEntries = Object.entries(socialRead.deltas ?? {}).slice(0, 4);

  const pendingConsequence = sessionState?.pending_consequence;
  const hasConsequence =
    pendingConsequence &&
    typeof pendingConsequence === "object" &&
    Object.keys(pendingConsequence).length > 0 &&
    Array.isArray((pendingConsequence as { options?: unknown }).options) &&
    ((pendingConsequence as { options: unknown[] }).options ?? []).length > 0;

  // ─── Render ─────────────────────────────────────────────────────
  return (
    <div className="flex h-full min-h-0">
      {showSessions && (
        <div
          className="fixed inset-0 z-30 bg-black/50 md:hidden"
          onClick={() => setShowSessions(false)}
          aria-hidden="true"
        />
      )}
      <SessionList
        sessions={sessions}
        activeId={activeSessionId}
        open={showSessions}
        onSelect={(id) => {
          setActiveSessionId(id);
          setShowSessions(false);
        }}
        onNew={() => {
          setShowSetup(true);
          setShowSessions(false);
        }}
        onDelete={(id) => deleteSession.mutate(id)}
        onRename={(id, title) => renameSession.mutate({ id, title })}
        loading={sessionsLoading}
      />

      <div className="flex-1 min-w-0 grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_340px]">
        <div className="flex flex-col min-w-0 border-r border-white/5">
          <PlayHeader
            activeSessionId={activeSessionId}
            activeSession={activeSession}
            sessionState={sessionState}
            messageCount={chat.messages.length}
            chatMode={chatMode}
            onChatModeChange={setChatMode}
            hasSelectedCharacter={!!selectedCharacter}
            onPatchTone={(tone) => patchTone.mutate({ tone })}
            onPatchRollModel={(rollModel) => patchRollModel.mutate({ roll_model: rollModel })}
            onSkipPreplay={() => skipPreplay.mutate()}
            skipPending={skipPreplay.isPending}
            onBeginStory={() => beginStory.mutate()}
            beginPending={beginStory.isPending}
            endingScene={endingScene}
            onEndScene={handleEndScene}
            onToggleSessions={() => setShowSessions((v) => !v)}
            sessionsOpen={showSessions}
            onTogglePanels={() => setShowPanels((v) => !v)}
            panelsOpen={showPanels}
          />

          {activeSessionId && <ConnectionBanner status={socketStatus} />}

          {!activeSessionId && !showSetup && (
            <div className="flex-1 flex flex-col items-center justify-center text-center space-y-4 px-4">
              <div className="w-16 h-16 rounded-2xl bg-cyan-500/10 border border-cyan-500/20 flex items-center justify-center shadow-cyan-glow">
                <Bot className="w-8 h-8 text-cyan-400" />
              </div>
              <div>
                <h2 className="text-lg font-semibold text-slate-200">MONITOR Play</h2>
                <p className="text-sm text-slate-600 mt-1 max-w-md">
                  Start a session, choose a setting and universe, then tell MONITOR what kind of story or opening scene you want in chat.
                </p>
              </div>
              <div className="flex flex-wrap items-center justify-center gap-3">
                <button
                  onClick={() => handleQuickStart()}
                  disabled={createSession.isPending}
                  className="btn-cyber"
                  title="One click — starts a session with default setting, tone and system"
                >
                  <Sparkles className="w-4 h-4" />
                  Quick start
                </button>
                <button onClick={() => setShowSetup(true)} className="btn-ghost px-4 py-2 text-sm">
                  New Play Session
                </button>
              </div>
            </div>
          )}

          {showSetup && (
            <div className="flex-1 overflow-y-auto px-3 py-4 sm:px-6">
              <SetupPanel
                isPending={createSession.isPending}
                initialMultiverseId={requestedMultiverseId}
                initialUniverseId={requestedUniverseId}
                onCreate={(payload: SetupPayload) => createSession.mutate(payload)}
                onQuickStart={handleQuickStart}
              />
            </div>
          )}

          {!showSetup && activeSessionId && (
            <>
              {/* Streamed message region — aria-live announces new GM text
                  to screen readers as it arrives (UX-6 / UX-7 a11y). */}
              <div aria-live="polite" className="flex-1 min-h-0 flex flex-col">
                <ChatList
                  messages={chat.messages}
                  streamingMsg={chat.streamingMsg}
                  isTyping={chat.isTyping}
                  sendFailure={friendlyTurnFailure(chat.sendFailure)}
                  pendingDiceRequest={chat.pendingDiceRequest}
                  renderBubble={(msg) => <PlayMessageBubble msg={msg} />}
                  onDiceResult={chat.submitDiceResult}
                  onServerRoll={chat.requestServerRoll}
                  rollModel={(activeSession?.roll_model ?? "tap") as "tap" | "manual" | "gm"}
                  onRetry={chat.retry}
                  onDismissFailure={chat.dismissFailure}
                />
              </div>

              <div className="space-y-2 px-3 pb-2 sm:px-6">
                <TurnWaitBar
                  waiting={turnActive}
                  isWaitingForGm={isWaitingForGm}
                  seconds={waitedSeconds}
                  onCancel={cancelTurn}
                />
                <TurnControls
                  messages={chat.messages}
                  disabled={turnActive}
                  onRegenerate={handleRegenerate}
                />
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
                {activeSessionId && suggestionsEnabled && visibleImageSuggestions.length > 0 && (
                  <div className="flex flex-wrap items-center gap-2 pt-2" data-testid="image-suggestions">
                    {visibleImageSuggestions.map((s) => (
                      <ImageSuggestionChip
                        key={s.suggestion_id}
                        suggestion={s}
                        sessionId={activeSessionId}
                        characterId={selectedCharacter?.id ?? null}
                        onSettled={settleImageSuggestion}
                      />
                    ))}
                  </div>
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
                  <div className="space-y-3">
                    {/* OOC-without-persona hint: when the toggle is in OOC
                        and no character is selected, the wrapping happens
                        silently in handleComposerSubmit. Surface that so
                        the player knows their toggle press actually does
                        something. Hidden when a persona is selected
                        because the send path then routes through the
                        character-chat handler instead. */}
                    {chatMode === "ooc" && !selectedCharacter && (
                      <div
                        data-testid="ooc-persona-hint"
                        className="text-[10px] text-amber-300/80 border border-amber-500/20 rounded-md px-2.5 py-1.5 bg-amber-500/5"
                      >
                        OOC mode without a persona — your message will be wrapped in{" "}
                        <code className="font-mono text-amber-200">((…))</code> and routed to the GM as out-of-character.
                      </div>
                    )}
                    {activeBenchmark?.starter_questions &&
                    activeBenchmark.starter_questions.length > 0 ? (
                      <div>
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
                    ) : null}
                  </div>
                }
              />
            </>
          )}
        </div>

        <PlaySidePanel
          open={showPanels}
          onClose={() => setShowPanels(false)}
          activeSession={activeSession}
          sessionState={sessionState}
          activeBenchmark={activeBenchmark}
          auditMeta={auditMeta}
          socialRead={socialRead}
          relationshipSnapshot={relationshipSnapshot}
          socialDeltaEntries={socialDeltaEntries}
          recapLines={recapLines}
          castSpeaker={castSpeaker}
          onSwitchSpeaker={(id, name) => {
            setCastSpeaker({ id, name });
            switchSpeaker.mutate({ id });
          }}
          selectedCharacter={selectedCharacter}
          onSelectCharacter={(_id, char) => setSelectedCharacter(char)}
          chatMode={chatMode}
          onChatModeChange={setChatMode}
        />
      </div>

      {showRecap && activeSessionId && (
        <RecapModal sessionId={activeSessionId} onClose={() => setShowRecap(false)} />
      )}
    </div>
  );
}
