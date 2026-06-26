"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { websocketBase } from "@/lib/api";

export type WsStatus = "connecting" | "connected" | "disconnected" | "reconnecting";

interface UseChatWebSocketOptions {
  /** Session ID to connect to. Pass null to disconnect. */
  sessionId: string | null;
  /** Called when a message is received from the WebSocket. */
  onMessage: (data: Record<string, unknown>) => void;
  /** Called when the connection opens. */
  onOpen?: () => void;
  /** Called when the connection closes unexpectedly. */
  onClose?: () => void;
  /** Called on connection error. */
  onError?: (event: Event) => void;
  /** Maximum reconnection backoff in ms (default 30_000). */
  maxBackoff?: number;
  /** Heartbeat interval in ms (default 30_000). Set to 0 to disable. */
  heartbeatMs?: number;
}

interface UseChatWebSocketReturn {
  /** Current connection status. */
  status: WsStatus;
  /** Send a message through the WebSocket. No-op if not connected. */
  send: (data: Record<string, unknown>) => void;
  /** The raw WebSocket ref (for advanced usage like readyState checks). */
  wsRef: React.RefObject<WebSocket | null>;
  /** Manually close the connection. */
  close: () => void;
  /** Manually reconnect (resets backoff). */
  reconnect: () => void;
}

export function useChatWebSocket({
  sessionId,
  onMessage,
  onOpen,
  onClose,
  onError,
  maxBackoff = 30_000,
  heartbeatMs = 30_000,
}: UseChatWebSocketOptions): UseChatWebSocketReturn {
  const [status, setStatus] = useState<WsStatus>("disconnected");
  const wsRef = useRef<WebSocket | null>(null);
  const retryCountRef = useRef(0);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const heartbeatTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const intentionalCloseRef = useRef(false);
  // Guards against connect() races (Fast Refresh, double-effect, manual
  // reconnect while a previous socket is still mid-handshake).
  const isConnectingRef = useRef(false);

  // Stable refs for callbacks to avoid re-creating the WebSocket on every render
  const onMessageRef = useRef(onMessage);
  onMessageRef.current = onMessage;
  const onOpenRef = useRef(onOpen);
  onOpenRef.current = onOpen;
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;
  const onErrorRef = useRef(onError);
  onErrorRef.current = onError;

  const clearTimers = useCallback(() => {
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
    if (heartbeatTimerRef.current) {
      clearInterval(heartbeatTimerRef.current);
      heartbeatTimerRef.current = null;
    }
  }, []);

  const startHeartbeat = useCallback(
    (ws: WebSocket) => {
      if (heartbeatMs <= 0) return;
      heartbeatTimerRef.current = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: "ping" }));
        }
      }, heartbeatMs);
    },
    [heartbeatMs],
  );

  const connect = useCallback(() => {
    if (!sessionId) return;

    // Idempotency guard — prevent double-socket races when connect() is
    // invoked while a previous socket is still mid-handshake (manual
    // reconnect, Fast Refresh, useEffect re-fire). The CONNECTING socket
    // will be torn down by the close() call below before we open a new one.
    if (isConnectingRef.current) return;
    isConnectingRef.current = true;

    // Close any existing connection
    if (wsRef.current) {
      wsRef.current.onopen = null;
      wsRef.current.onmessage = null;
      wsRef.current.onclose = null;
      wsRef.current.onerror = null;
      if (wsRef.current.readyState === WebSocket.OPEN || wsRef.current.readyState === WebSocket.CONNECTING) {
        wsRef.current.close();
      }
      wsRef.current = null;
    }

    clearTimers();
    intentionalCloseRef.current = false;
    setStatus("connecting");

    const url = `${websocketBase()}/api/chat/ws/${sessionId}`;
    let ws: WebSocket;
    try {
      ws = new WebSocket(url);
    } catch (err) {
      isConnectingRef.current = false;
      setStatus("disconnected");
      onErrorRef.current?.(new Event("ws-construct-failed"));
      return;
    }
    wsRef.current = ws;

    ws.onopen = () => {
      isConnectingRef.current = false;
      retryCountRef.current = 0;
      setStatus("connected");
      startHeartbeat(ws);
      onOpenRef.current?.();
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        // Ignore pong messages (heartbeat response)
        if (data.type === "pong") return;
        onMessageRef.current(data);
      } catch {
        // Non-JSON message, ignore
      }
    };

    ws.onclose = (event) => {
      isConnectingRef.current = false;
      clearTimers();
      if (intentionalCloseRef.current) {
        setStatus("disconnected");
        onCloseRef.current?.();
        return;
      }

      // Unexpected close — attempt reconnection
      setStatus("reconnecting");
      onCloseRef.current?.();

      const backoff = Math.min(1000 * 2 ** retryCountRef.current, maxBackoff);
      const jitter = Math.random() * 500;
      retryCountRef.current += 1;

      reconnectTimerRef.current = setTimeout(() => {
        if (!intentionalCloseRef.current && sessionId) {
          connect();
        }
      }, backoff + jitter);
    };

    ws.onerror = (event) => {
      isConnectingRef.current = false;
      onErrorRef.current?.(event);
    };
  }, [sessionId, maxBackoff, clearTimers, startHeartbeat]);

  // Connect when sessionId changes
  useEffect(() => {
    if (sessionId) {
      connect();
    } else {
      // No session — close any existing connection
      intentionalCloseRef.current = true;
      clearTimers();
      if (wsRef.current) {
        wsRef.current.onopen = null;
        wsRef.current.onmessage = null;
        wsRef.current.onclose = null;
        wsRef.current.onerror = null;
        if (wsRef.current.readyState === WebSocket.OPEN || wsRef.current.readyState === WebSocket.CONNECTING) {
          wsRef.current.close();
        }
        wsRef.current = null;
      }
      setStatus("disconnected");
    }

    return () => {
      intentionalCloseRef.current = true;
      isConnectingRef.current = false;
      clearTimers();
      if (wsRef.current) {
        wsRef.current.onopen = null;
        wsRef.current.onmessage = null;
        wsRef.current.onclose = null;
        wsRef.current.onerror = null;
        if (wsRef.current.readyState === WebSocket.OPEN || wsRef.current.readyState === WebSocket.CONNECTING) {
          wsRef.current.close();
        }
        wsRef.current = null;
      }
    };
  }, [sessionId, connect, clearTimers]);

  const send = useCallback((data: Record<string, unknown>) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(data));
    }
  }, []);

  const close = useCallback(() => {
    intentionalCloseRef.current = true;
    isConnectingRef.current = false;
    clearTimers();
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    setStatus("disconnected");
  }, [clearTimers]);

  const reconnect = useCallback(() => {
    retryCountRef.current = 0;
    intentionalCloseRef.current = false;
    connect();
  }, [connect]);

  return { status, send, wsRef, close, reconnect };
}