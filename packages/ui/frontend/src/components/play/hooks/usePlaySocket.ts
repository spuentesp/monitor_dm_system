"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { useChatSession } from "@/features/chat";
import type { ChatStatus, UseChatSessionReturn } from "@/features/chat";
import { PLAY_KEYS } from "@/lib/query-keys";

export interface UsePlaySocketOptions {
  sessionId: string | null;
}

export interface UsePlaySocketReturn {
  /** The underlying streaming/chat state machine (messages, send, retry…). */
  chat: UseChatSessionReturn;
  /** Live WebSocket connection status. */
  status: ChatStatus;
  /** True while the socket is connecting or reconnecting (backoff). */
  isConnectionLost: boolean;
  /** True while a turn is in flight (waiting for, or streaming, the GM reply). */
  turnActive: boolean;
  /** True while waiting for the GM's first token — the "GM is thinking" state. */
  isWaitingForGm: boolean;
  /** Seconds elapsed since the current turn started. */
  waitedSeconds: number;
  /**
   * Abort the local wait (watchdog + typing indicator + streaming bubble).
   * The chat WS protocol has no server-side cancel frame, so this only stops
   * the client's wait — the server may still finish the turn.
   */
  cancelTurn: () => void;
}

/**
 * Wraps useChatSession with the connection/waiting presentation state the
 * play console needs (UX-6):
 *
 * - reconnect status (the underlying useChatWebSocket already reconnects
 *   automatically with exponential backoff + jitter; this hook surfaces it)
 * - a "GM is thinking / writing" elapsed-time counter for the active turn
 * - a local cancel for the in-flight wait
 *
 * Owns the onTurnSettled invalidation of the sessions list so callers don't
 * have to wire it.
 */
export function usePlaySocket({ sessionId }: UsePlaySocketOptions): UsePlaySocketReturn {
  const qc = useQueryClient();

  const chat = useChatSession({
    sessionId,
    onTurnSettled: () => {
      qc.invalidateQueries({ queryKey: PLAY_KEYS.sessions });
    },
  });

  const { status, isTyping, streamingMsg } = chat;
  const turnActive = isTyping || streamingMsg !== null;
  const isWaitingForGm = isTyping && !streamingMsg;

  const turnStartedAtRef = useRef<number | null>(null);
  const [waitedSeconds, setWaitedSeconds] = useState(0);

  useEffect(() => {
    if (!turnActive) {
      turnStartedAtRef.current = null;
      setWaitedSeconds(0);
      return;
    }
    if (turnStartedAtRef.current === null) {
      turnStartedAtRef.current = Date.now();
    }
    const startedAt = turnStartedAtRef.current;
    setWaitedSeconds(Math.max(0, Math.floor((Date.now() - startedAt) / 1000)));
    const timer = setInterval(() => {
      setWaitedSeconds(Math.max(0, Math.floor((Date.now() - startedAt) / 1000)));
    }, 1000);
    return () => clearInterval(timer);
  }, [turnActive]);

  const cancelTurn = useCallback(() => {
    turnStartedAtRef.current = null;
    setWaitedSeconds(0);
    chat.stop();
  }, [chat]);

  return {
    chat,
    status,
    isConnectionLost: status !== "connected",
    turnActive,
    isWaitingForGm,
    waitedSeconds,
    cancelTurn,
  };
}
