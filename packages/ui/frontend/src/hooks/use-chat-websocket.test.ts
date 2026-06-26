// @vitest-environment happy-dom
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useChatWebSocket } from "./use-chat-websocket";

// Stable URL so the hook's WS construction doesn't depend on the real
// api module's environment detection.
vi.mock("@/lib/api", () => ({
  websocketBase: () => "ws://test",
}));

// ─── Fake WebSocket ──────────────────────────────────────────────────
// Replaces the global WebSocket so the hook can be exercised without a
// real network. Each instance tracks its constructed URL, exposes a
// `simulate*` helper to fire events, and counts how many sockets the
// hook has tried to open.

interface FakeSocket {
  url: string;
  readyState: number;
  closed: boolean;
  sent: string[];
  onopen: ((ev: Event) => void) | null;
  onclose: ((ev: CloseEvent) => void) | null;
  onerror: ((ev: Event) => void) | null;
  onmessage: ((ev: MessageEvent) => void) | null;
  close: () => void;
}

let constructed: FakeSocket[] = [];

class FakeWebSocket {
  static OPEN = 1;
  static CONNECTING = 0;
  static CLOSING = 2;
  static CLOSED = 3;

  url: string;
  readyState = FakeWebSocket.CONNECTING;
  closed = false;
  sent: string[] = [];
  onopen: ((ev: Event) => void) | null = null;
  onclose: ((ev: CloseEvent) => void) | null = null;
  onerror: ((ev: Event) => void) | null = null;
  onmessage: ((ev: MessageEvent) => void) | null = null;

  constructor(url: string) {
    this.url = url;
    constructed.push(this as unknown as FakeSocket);
  }

  close() {
    if (this.closed) return;
    this.closed = true;
    this.readyState = FakeWebSocket.CLOSED;
    // Schedule the onclose callback so the hook's effects can run.
    queueMicrotask(() => this.onclose?.(new CloseEvent("close")));
  }

  send(payload: string) {
    this.sent.push(payload);
  }

  // Test helpers ────────────────────────────────────────────────
  simulateOpen() {
    this.readyState = FakeWebSocket.OPEN;
    this.onopen?.(new Event("open"));
  }

  simulateMessage(data: unknown) {
    this.onmessage?.(new MessageEvent("message", { data: JSON.stringify(data) }));
  }

  simulateClose() {
    this.close();
  }

  simulateError() {
    this.onerror?.(new Event("error"));
  }
}

beforeEach(() => {
  constructed = [];
  // FakeWebSocket's static constants are read at module init; this
  // matches the global WebSocket shape closely enough for our hook.
  (globalThis as unknown as { WebSocket: typeof FakeWebSocket }).WebSocket = FakeWebSocket as unknown as typeof WebSocket;
});

afterEach(() => {
  vi.restoreAllMocks();
});

// ─── Tests ───────────────────────────────────────────────────────────

describe("useChatWebSocket — P0.7 connect race guard", () => {
  it("connects when sessionId becomes non-null", () => {
    const onMessage = vi.fn();
    renderHook(() =>
      useChatWebSocket({ sessionId: "sess-1", onMessage }),
    );
    expect(constructed.length).toBe(1);
    expect(constructed[0].url).toBe("ws://test/api/chat/ws/sess-1");
  });

  it("opens exactly one socket when connect() is invoked twice in a row", async () => {
    const onMessage = vi.fn();
    const { result } = renderHook(() =>
      useChatWebSocket({ sessionId: "sess-1", onMessage }),
    );
    expect(constructed.length).toBe(1);

    // Manual reconnect while the first socket is still mid-handshake.
    await act(async () => {
      result.current.reconnect();
    });

    // The guard rejects the second invocation while the first is still
    // connecting (isConnectingRef.current === true). Exactly one socket
    // exists — the duplicate was a no-op.
    expect(constructed.length).toBe(1);
  });

  it("allows a fresh connect() after the first socket opens", async () => {
    const onMessage = vi.fn();
    const { result } = renderHook(() =>
      useChatWebSocket({ sessionId: "sess-1", onMessage }),
    );

    await act(async () => {
      constructed[0].simulateOpen();
    });

    expect(result.current.status).toBe("connected");

    await act(async () => {
      result.current.reconnect();
    });

    // After the first socket opened, isConnectingRef was reset, so a
    // reconnect closes the old socket and opens a new one.
    expect(constructed.length).toBe(2);
  });

  it("reset isConnectingRef after an error so subsequent reconnects work", async () => {
    vi.useFakeTimers();
    try {
      const onMessage = vi.fn();
      const { result } = renderHook(() =>
        useChatWebSocket({ sessionId: "sess-1", onMessage }),
      );

      // The browser fires onclose after onerror. After error, the hook
      // sets status to "reconnecting" and schedules a backoff timer.
      await act(async () => {
        constructed[0].simulateError();
        constructed[0].simulateClose();
      });

      // Status flips to reconnecting (browser typically closes after error).
      expect(["disconnected", "reconnecting"]).toContain(result.current.status);

      // Advance past the reconnect backoff (1s initial + jitter).
      await act(async () => {
        vi.advanceTimersByTime(2000);
      });

      // The scheduled reconnect fires — a fresh socket is constructed.
      expect(constructed.length).toBeGreaterThanOrEqual(2);
    } finally {
      vi.useRealTimers();
    }
  });

  it("close() resets isConnectingRef so reconnect can fire immediately", async () => {
    const onMessage = vi.fn();
    const { result } = renderHook(() =>
      useChatWebSocket({ sessionId: "sess-1", onMessage }),
    );
    expect(constructed.length).toBe(1);

    await act(async () => {
      result.current.close();
    });

    await act(async () => {
      result.current.reconnect();
    });

    expect(constructed.length).toBe(2);
  });

  it("delivers messages to the onMessage callback", async () => {
    const onMessage = vi.fn();
    renderHook(() =>
      useChatWebSocket({ sessionId: "sess-1", onMessage }),
    );

    await act(async () => {
      constructed[0].simulateOpen();
      constructed[0].simulateMessage({ type: "token", message_id: "m1", token: "hello" });
    });

    expect(onMessage).toHaveBeenCalledWith({ type: "token", message_id: "m1", token: "hello" });
  });

  it("ignores heartbeat pongs", async () => {
    const onMessage = vi.fn();
    renderHook(() =>
      useChatWebSocket({ sessionId: "sess-1", onMessage, heartbeatMs: 30_000 }),
    );

    await act(async () => {
      constructed[0].simulateOpen();
      constructed[0].simulateMessage({ type: "pong" });
    });

    expect(onMessage).not.toHaveBeenCalled();
  });

  it("does not deliver non-JSON payloads (no throw)", async () => {
    const onMessage = vi.fn();
    renderHook(() =>
      useChatWebSocket({ sessionId: "sess-1", onMessage }),
    );

    await act(async () => {
      constructed[0].simulateOpen();
      // Bypass the JSON.stringify helper: deliver raw text.
      constructed[0].onmessage?.(new MessageEvent("message", { data: "not-json" }));
    });

    expect(onMessage).not.toHaveBeenCalled();
  });

  it("send() is a no-op when not connected", () => {
    const onMessage = vi.fn();
    const { result } = renderHook(() =>
      useChatWebSocket({ sessionId: "sess-1", onMessage }),
    );

    // Socket is still CONNECTING.
    act(() => {
      result.current.send({ type: "message", content: "hi" });
    });

    expect(constructed[0].sent).toEqual([]);
  });

  it("send() forwards JSON to the open socket", async () => {
    const onMessage = vi.fn();
    const { result } = renderHook(() =>
      useChatWebSocket({ sessionId: "sess-1", onMessage }),
    );

    await act(async () => {
      constructed[0].simulateOpen();
      result.current.send({ type: "ping" });
    });

    expect(constructed[0].sent).toEqual([JSON.stringify({ type: "ping" })]);
  });

  it("disconnects cleanly when sessionId becomes null", async () => {
    const onMessage = vi.fn();
    const { rerender } = renderHook(
      ({ sid }: { sid: string | null }) =>
        useChatWebSocket({ sessionId: sid, onMessage }),
      { initialProps: { sid: "sess-1" as string | null } },
    );
    expect(constructed.length).toBe(1);

    await act(async () => {
      constructed[0].simulateOpen();
    });

    rerender({ sid: null });

    // The cleanup closes the socket and clears handlers.
    expect(constructed[0].closed).toBe(true);
  });
});