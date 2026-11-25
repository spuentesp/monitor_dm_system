"use client";

import { useEffect, useState } from "react";
import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
} from "@tanstack/react-query";

import { chatApi } from "@/lib/api";
import { PLAY_KEYS } from "@/lib/query-keys";
import { useWorldContext } from "@/lib/world-context";
import type { ChatSessionState, Message, PlaytestBenchmark, Session } from "@/lib/types";

export type CreateSessionInput = Parameters<typeof chatApi.createSession>[0];

export interface UsePlaySessionOptions {
  /** Session id from the URL (`?session=`), if any. */
  requestedSessionId: string | null;
  /** Called when the deep-linked session id matches a real session and is
   *  auto-selected (the original console closed the setup panel here). */
  onDeepLinkSelected?: () => void;
  /** Called after a session is created through this hook (close setup). */
  onSessionCreated?: () => void;
}

export interface UsePlaySessionReturn {
  sessions: Session[];
  sessionsLoading: boolean;
  activeSessionId: string | null;
  setActiveSessionId: (id: string | null) => void;
  activeSession: Session | null;
  sessionState: ChatSessionState | undefined;
  benchmarkCatalog: PlaytestBenchmark[];
  createSession: UseMutationResult<Session, Error, CreateSessionInput>;
  deleteSession: UseMutationResult<void, Error, string>;
  renameSession: UseMutationResult<Session, Error, { id: string; title: string }>;
  patchTone: UseMutationResult<Session, Error, { tone: string }>;
  patchRollModel: UseMutationResult<Session, Error, { roll_model: string }>;
  switchSpeaker: UseMutationResult<Session, Error, { id: string }>;
  skipPreplay: UseMutationResult<Message, Error, void>;
  beginStory: UseMutationResult<Message, Error, void>;
}

/**
 * Owns session-list state for the play console: the sessions query, the
 * active-session selection (deep link → first session), the session-state /
 * benchmark queries, and every session mutation (create, delete, rename,
 * tone, roll model, speaker switch, skip-preplay, begin-story).
 *
 * Extracted from PlayConsole.tsx (UX-6 split) — behavior is unchanged.
 */
export function usePlaySession({
  requestedSessionId,
  onDeepLinkSelected,
  onSessionCreated,
}: UsePlaySessionOptions): UsePlaySessionReturn {
  const qc = useQueryClient();
  const world = useWorldContext();

  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);

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
      onDeepLinkSelected?.();
      return;
    }
    if (!activeSessionId && sessions[0]?.id) {
      setActiveSessionId(sessions[0].id);
    }
  }, [sessions, activeSessionId, requestedSessionId, onDeepLinkSelected]);

  const { data: sessionState } = useQuery<ChatSessionState>({
    queryKey: PLAY_KEYS.state(activeSessionId),
    queryFn: () => chatApi.getSessionState(activeSessionId!),
    enabled: !!activeSessionId,
  });

  // ─── Mutations ───────────────────────────────────────────────────
  const createSession = useMutation({
    mutationFn: chatApi.createSession,
    onSuccess: (session) => {
      qc.invalidateQueries({ queryKey: PLAY_KEYS.sessions });
      setActiveSessionId(session.id);
      onSessionCreated?.();
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

  const patchRollModel = useMutation({
    mutationFn: ({ roll_model }: { roll_model: string }) =>
      chatApi.patchSession(activeSessionId!, { roll_model }),
    onSuccess: () => qc.invalidateQueries({ queryKey: PLAY_KEYS.sessions }),
  });

  // [P-16] Cast panel speaker switch: SessionPatch.speaker_character_id makes
  // the switch immediate (join Task 7) — no waiting for the next message.
  const switchSpeaker = useMutation({
    mutationFn: ({ id }: { id: string }) =>
      chatApi.patchSession(activeSessionId!, { speaker_character_id: id }),
    onSuccess: () => qc.invalidateQueries({ queryKey: PLAY_KEYS.sessions }),
  });

  // [G-1](c) Skip-to-play: jump from Session Zero / char creation straight
  // into active_play. Disabled while pending.
  const skipPreplay = useMutation({
    mutationFn: () => chatApi.skipPreplay(activeSessionId!),
    onSuccess: () => {
      // Refresh session-state so the new PhaseChip + new GM message appear.
      // (Key kept verbatim from the pre-split PlayConsole — it predates
      // PLAY_KEYS.state; the WS `done` handler is what actually refreshes
      // the state query today.)
      qc.invalidateQueries({ queryKey: ["session-state", activeSessionId] });
      qc.invalidateQueries({ queryKey: ["play-sessions"] });
    },
  });

  // [P-19] Begin Story — confirm Session Zero agreements and bootstrap the
  // opening narration. Only meaningful once agreements are awaiting
  // confirmation.
  const beginStory = useMutation({
    mutationFn: () => chatApi.beginStory(activeSessionId!),
    onSuccess: () => {
      // Key kept verbatim from the pre-split PlayConsole (see skipPreplay).
      qc.invalidateQueries({ queryKey: ["session-state", activeSessionId] });
      qc.invalidateQueries({ queryKey: ["play-sessions"] });
    },
  });

  const renameSession = useMutation({
    mutationFn: ({ id, title }: { id: string; title: string }) =>
      chatApi.patchSession(id, { title }),
    onSuccess: () => qc.invalidateQueries({ queryKey: PLAY_KEYS.sessions }),
  });

  const activeSession = sessions.find((s) => s.id === activeSessionId) ?? null;

  return {
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
  };
}
