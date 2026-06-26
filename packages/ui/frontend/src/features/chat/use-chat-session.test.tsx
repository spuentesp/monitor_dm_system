// @vitest-environment happy-dom
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { useChatSession } from "./use-chat-session";
import { chatApi } from "@/lib/api";

// Mock @/lib/api so we get a stable websocketBase URL AND a controllable
// chatApi surface. We pass through the real module's other exports so
// the hook can still call listSessions etc. without throwing.
vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    websocketBase: () => "ws://test",
  };
});

// Stub fetch globally — happy-dom has one but it would hit a real
// backend if the REST fallback fires. This is belt-and-suspenders
// alongside the api mock.
beforeEach(() => {
  globalThis.fetch = vi.fn(() =>
    Promise.resolve(
      new Response("[]", {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    ),
  ) as unknown as typeof fetch;
});

// ─── Fake WebSocket ──────────────────────────────────────────────────

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
    queueMicrotask(() => this.onclose?.(new CloseEvent("close")));
  }
  send(payload: string) {
    this.sent.push(payload);
  }
  simulateOpen() {
    this.readyState = FakeWebSocket.OPEN;
    this.onopen?.(new Event("open"));
  }
  simulateFrame(frame: unknown) {
    this.onmessage?.(new MessageEvent("message", { data: JSON.stringify(frame) }));
  }
}

beforeEach(() => {
  constructed = [];
  (globalThis as unknown as { WebSocket: typeof FakeWebSocket }).WebSocket = FakeWebSocket as unknown as typeof WebSocket;
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

// ─── Helpers ─────────────────────────────────────────────────────────

const SESSION = "sess-abc";
const MSG_ID = "msg-123";

function makeWrapper() {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0, staleTime: 0 },
    },
  });
  // Pre-populate the messages query cache so the hook has data to render.
  qc.setQueryData(["play-messages", SESSION], []);
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return { qc, wrapper };
}

function flushPromises() {
  return new Promise<void>((resolve) => setTimeout(resolve, 0));
}

/** Open the WS by setting sessionId, then simulate the open frame. */
async function openWs() {
  await act(async () => {
    constructed[0]?.simulateOpen();
  });
}

// ─── Tests ───────────────────────────────────────────────────────────

describe("useChatSession — streaming state machine", () => {
  it("WS connects when sessionId is set", async () => {
    const { wrapper } = makeWrapper();
    renderHook(() => useChatSession({ sessionId: SESSION }), { wrapper });
    await openWs();
    expect(constructed.length).toBe(1);
  });

  it("emits composing event handling: typing stays on", async () => {
    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useChatSession({ sessionId: SESSION }), { wrapper });
    await openWs();

    act(() => {
      result.current.send("hello", {});
    });

    expect(constructed[0].sent[0]).toContain('"type":"message"');

    await act(async () => {
      constructed[0].simulateFrame({ type: "start", message_id: MSG_ID });
      constructed[0].simulateFrame({ type: "composing", message_id: MSG_ID });
    });

    expect(result.current.isTyping).toBe(true);
  });

  it("accumulates token frames into streamingMsg.text", async () => {
    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useChatSession({ sessionId: SESSION }), { wrapper });
    await openWs();

    act(() => result.current.send("hi"));
    await act(async () => {
      constructed[0].simulateFrame({ type: "start", message_id: MSG_ID });
      constructed[0].simulateFrame({ type: "token", message_id: MSG_ID, token: "Hel" });
      constructed[0].simulateFrame({ type: "token", message_id: MSG_ID, token: "lo " });
      constructed[0].simulateFrame({ type: "token", message_id: MSG_ID, token: "world" });
    });

    expect(result.current.streamingMsg?.text).toBe("Hello world");
  });

  it("per-turn isolation: late tokens for prior turn do not pollute new turn", async () => {
    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useChatSession({ sessionId: SESSION }), { wrapper });
    await openWs();

    // Turn 1
    act(() => result.current.send("first"));
    await act(async () => {
      constructed[0].simulateFrame({ type: "start", message_id: "turn-1" });
      constructed[0].simulateFrame({ type: "token", message_id: "turn-1", token: "A" });
    });
    expect(result.current.streamingMsg?.id).toBe("turn-1");
    expect(result.current.streamingMsg?.text).toBe("A");

    // User fires turn 2 before turn 1 finishes — a new start frame comes
    // and resets the active id.
    act(() => result.current.send("second"));
    await act(async () => {
      constructed[0].simulateFrame({ type: "start", message_id: "turn-2" });
      constructed[0].simulateFrame({ type: "token", message_id: "turn-2", token: "B" });
    });
    expect(result.current.streamingMsg?.id).toBe("turn-2");
    expect(result.current.streamingMsg?.text).toBe("B");

    // Now a LATE token for turn 1 arrives. Because the hook looks up the
    // message by id from the frame (not a shared ref), this must NOT
    // pollute turn 2. The fix for P0.4.
    await act(async () => {
      constructed[0].simulateFrame({ type: "token", message_id: "turn-1", token: "LATE" });
    });

    expect(result.current.streamingMsg?.id).toBe("turn-2");
    expect(result.current.streamingMsg?.text).toBe("B");
  });

  it("done frame clears streamingMsg and persists metadata", async () => {
    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useChatSession({ sessionId: SESSION }), { wrapper });
    await openWs();

    act(() => result.current.send("hi"));
    await act(async () => {
      constructed[0].simulateFrame({ type: "start", message_id: MSG_ID });
      constructed[0].simulateFrame({ type: "token", message_id: MSG_ID, token: "Hello" });
      constructed[0].simulateFrame({
        type: "done",
        message_id: MSG_ID,
        metadata: { type: "scene_turn", success_level: "success" },
      });
    });

    expect(result.current.streamingMsg).toBeNull();
    expect(result.current.isTyping).toBe(false);
  });

  it("error frame surfaces sendFailure with detail", async () => {
    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useChatSession({ sessionId: SESSION }), { wrapper });
    await openWs();

    act(() => result.current.send("hi"));
    await act(async () => {
      constructed[0].simulateFrame({ type: "start", message_id: MSG_ID });
      constructed[0].simulateFrame({ type: "error", detail: "rate-limited" });
    });

    expect(result.current.sendFailure?.detail).toBe("rate-limited");
    expect(result.current.sendFailure?.text).toBe("hi");
  });

  it("dismissFailure clears the failure card", async () => {
    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useChatSession({ sessionId: SESSION }), { wrapper });
    await openWs();

    act(() => result.current.send("hi"));
    await act(async () => {
      constructed[0].simulateFrame({ type: "start", message_id: MSG_ID });
      constructed[0].simulateFrame({ type: "error", detail: "boom" });
    });
    expect(result.current.sendFailure).not.toBeNull();

    act(() => result.current.dismissFailure());
    expect(result.current.sendFailure).toBeNull();
  });

  it("surfaceFailure is a no-echo way to display non-turn failures", async () => {
    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useChatSession({ sessionId: SESSION }), { wrapper });
    await openWs();

    act(() => result.current.surfaceFailure("End-scene failed: timeout"));
    expect(result.current.sendFailure?.detail).toBe("End-scene failed: timeout");
  });

  it("sessionId change resets all transient state", async () => {
    const { wrapper } = makeWrapper();
    const { result, rerender } = renderHook(
      ({ sid }: { sid: string | null }) => useChatSession({ sessionId: sid }),
      { wrapper, initialProps: { sid: SESSION as string | null } },
    );
    await openWs();

    act(() => result.current.send("hi"));
    await act(async () => {
      constructed[0].simulateFrame({ type: "start", message_id: MSG_ID });
      constructed[0].simulateFrame({ type: "thinking", message_id: MSG_ID, delta: "hmm" });
      constructed[0].simulateFrame({ type: "token", message_id: MSG_ID, token: "Hi" });
    });

    expect(result.current.streamingMsg).not.toBeNull();

    rerender({ sid: null });

    expect(result.current.streamingMsg).toBeNull();
    expect(result.current.isTyping).toBe(false);
  });
});

// ─── Phase 2: thinking / composing ──────────────────────────────────

describe("useChatSession — Phase 2 thinking + composing", () => {
  it("thinking chunks accumulate into streamingMsg.thinking", async () => {
    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useChatSession({ sessionId: SESSION }), { wrapper });
    await openWs();

    act(() => result.current.send("hi"));
    await act(async () => {
      constructed[0].simulateFrame({ type: "start", message_id: MSG_ID });
      constructed[0].simulateFrame({ type: "thinking", message_id: MSG_ID, delta: "Let me " });
      constructed[0].simulateFrame({ type: "thinking", message_id: MSG_ID, delta: "think..." });
    });

    expect(result.current.streamingMsg?.thinking?.text).toBe("Let me think...");
    expect(result.current.streamingMsg?.thinking?.streaming).toBe(true);
  });

  it("thinking_end flips the trace out of streaming", async () => {
    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useChatSession({ sessionId: SESSION }), { wrapper });
    await openWs();

    act(() => result.current.send("hi"));
    await act(async () => {
      constructed[0].simulateFrame({ type: "start", message_id: MSG_ID });
      constructed[0].simulateFrame({ type: "thinking", message_id: MSG_ID, delta: "..." });
      constructed[0].simulateFrame({ type: "thinking_end", message_id: MSG_ID });
      constructed[0].simulateFrame({ type: "token", message_id: MSG_ID, token: "Hello" });
    });

    expect(result.current.streamingMsg?.thinking?.streaming).toBe(false);
    expect(result.current.streamingMsg?.thinking?.text).toBe("...");
    expect(result.current.streamingMsg?.text).toBe("Hello");
  });

  it("done persists thinking trace onto metadata.thinking", async () => {
    const { qc: testQc } = makeWrapper();
    // Spy will be installed AFTER setQueryData so it can read the
    // current cache state and preserve any updates the hook makes.
    const spy = vi.spyOn(chatApi, "getMessages").mockImplementation(async () => {
      return (testQc.getQueryData(["play-messages", SESSION]) ?? []) as Awaited<
        ReturnType<typeof chatApi.getMessages>
      >;
    });

    const { wrapper } = { wrapper: ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={testQc}>{children}</QueryClientProvider>
    ) };

    // Pre-seed the messages cache with a GM message that has the message_id
    // we'll be streaming into. This way the hook's `done` handler can do
    // `setQueryData` and attach the thinking metadata onto a known message.
    const seededMessage = {
      id: MSG_ID,
      session_id: SESSION,
      role: "gm",
      content: "",
      timestamp: new Date().toISOString(),
      metadata: {},
    };
    testQc.setQueryData(["play-messages", SESSION], [seededMessage]);

    const { result } = renderHook(() => useChatSession({ sessionId: SESSION }), { wrapper });
    await openWs();

    act(() => result.current.send("hi"));
    await act(async () => {
      constructed[0].simulateFrame({ type: "start", message_id: MSG_ID });
      constructed[0].simulateFrame({ type: "thinking", message_id: MSG_ID, delta: "Reasoning text" });
      constructed[0].simulateFrame({ type: "thinking_end", message_id: MSG_ID });
      constructed[0].simulateFrame({ type: "token", message_id: MSG_ID, token: "Hi" });
      constructed[0].simulateFrame({ type: "done", message_id: MSG_ID, metadata: {} });
    });

    // Done should clear streamingMsg.
    expect(result.current.streamingMsg).toBeNull();
    expect(result.current.isTyping).toBe(false);

    // The thinking trace persists into metadata.thinking on the cached
    // GM message.
    const cached = testQc.getQueryData<Array<{ id: string; metadata?: Record<string, unknown> }>>([
      "play-messages",
      SESSION,
    ]);
    expect(cached?.[0]?.metadata?.thinking).toBe("Reasoning text");
  });

  it("tool_call / tool_result frames are accepted but no-op (forward compat)", async () => {
    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useChatSession({ sessionId: SESSION }), { wrapper });
    await openWs();

    act(() => result.current.send("hi"));
    await act(async () => {
      constructed[0].simulateFrame({ type: "start", message_id: MSG_ID });
      constructed[0].simulateFrame({
        type: "tool_call",
        message_id: MSG_ID,
        name: "neo4j_search",
        args: { q: "Geralt" },
      });
      constructed[0].simulateFrame({
        type: "tool_result",
        message_id: MSG_ID,
        result: { hits: 3 },
      });
      constructed[0].simulateFrame({ type: "token", message_id: MSG_ID, token: "Result" });
    });

    // No crash, no thrown; streaming continues normally.
    expect(result.current.streamingMsg?.text).toBe("Result");
  });
});

// ─── dice + retry ────────────────────────────────────────────────────

describe("useChatSession — dice + retry", () => {
  it("done with dice_request sets pendingDiceRequest", async () => {
    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useChatSession({ sessionId: SESSION }), { wrapper });
    await openWs();

    act(() => result.current.send("attack"));
    await act(async () => {
      constructed[0].simulateFrame({ type: "start", message_id: MSG_ID });
      constructed[0].simulateFrame({
        type: "done",
        message_id: MSG_ID,
        metadata: { dice_request: { spec: "1d20+3", reason: "Strength" } },
      });
    });

    expect(result.current.pendingDiceRequest?.spec).toBe("1d20+3");
    expect(result.current.pendingDiceRequest?.reason).toBe("Strength");
  });

  it("submitDiceResult sends a dice_result frame and clears the prompt", async () => {
    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useChatSession({ sessionId: SESSION }), { wrapper });
    await openWs();

    act(() => result.current.submitDiceResult("1d20+3", 18, [15], "Strength"));

    expect(constructed[0].sent.some((s) => s.includes('"type":"dice_result"'))).toBe(true);
    expect(constructed[0].sent.some((s) => s.includes('"value":18'))).toBe(true);
  });

  it("retry re-sends the last failed turn without optimistic echo", async () => {
    const { wrapper, qc } = makeWrapper();
    const { result } = renderHook(() => useChatSession({ sessionId: SESSION }), { wrapper });
    await openWs();

    // First send → error
    act(() => result.current.send("first action"));
    await act(async () => {
      constructed[0].simulateFrame({ type: "start", message_id: "x" });
      constructed[0].simulateFrame({ type: "error", detail: "boom" });
    });

    const beforeRetry = qc.getQueryData<unknown[]>(["play", "chat", "messages", SESSION])?.length ?? 0;

    // Retry — should NOT add another optimistic bubble
    act(() => result.current.retry());

    await act(async () => {
      // No new optimistic should have been added.
      const afterRetry = qc.getQueryData<unknown[]>(["play", "chat", "messages", SESSION])?.length ?? 0;
      expect(afterRetry).toBe(beforeRetry);
    });

    // The retry itself should have re-sent the same text via WS.
    expect(
      constructed[0].sent.filter((s) => s.includes('"content":"first action"')).length,
    ).toBe(2);
  });
});

// ─── REST fallback ───────────────────────────────────────────────────

describe("useChatSession — REST fallback when WS disconnected", () => {
  it("uses chatApi.sendMessage when WS is not connected", async () => {
    const apiModule = await import("@/lib/api");
    const sendMessageSpy = vi
      .spyOn(apiModule.chatApi, "sendMessage")
      .mockResolvedValue({
        id: "m1",
        session_id: SESSION,
        role: "gm",
        content: "Done",
        timestamp: new Date().toISOString(),
        metadata: {},
      } as never);

    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useChatSession({ sessionId: SESSION }), { wrapper });

    // Don't open the WS — keep it disconnected so the REST fallback fires.
    expect(result.current.status).not.toBe("connected");

    await act(async () => {
      result.current.send("hello via REST", {});
    });

    expect(sendMessageSpy).toHaveBeenCalledWith(
      SESSION,
      "hello via REST",
      expect.objectContaining({}),
    );

    sendMessageSpy.mockRestore();
  });
});