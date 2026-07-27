// @vitest-environment happy-dom
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { useChatSession } from "./use-chat-session";

beforeEach(() => {
  globalThis.fetch = vi.fn(() =>
    Promise.resolve(new Response("[]", { status: 200, headers: { "Content-Type": "application/json" } })),
  ) as unknown as typeof fetch;
});

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return { ...actual, websocketBase: () => "ws://test" };
});

class FakeWebSocket {
  static OPEN = 1;
  static CONNECTING = 0;
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
    FakeWebSocket.constructed.push(this as unknown as FakeWebSocket);
  }
  close() { this.closed = true; this.readyState = 3; queueMicrotask(() => this.onclose?.(new CloseEvent("close"))); }
  send(p: string) { this.sent.push(p); }
  simulateOpen() { this.readyState = 1; this.onopen?.(new Event("open")); }
  simulateFrame(f: unknown) { this.onmessage?.(new MessageEvent("message", { data: JSON.stringify(f) })); }
  static constructed: FakeWebSocket[] = [];
}

beforeEach(() => {
  FakeWebSocket.constructed = [];
  (globalThis as unknown as { WebSocket: typeof FakeWebSocket }).WebSocket = FakeWebSocket as unknown as typeof WebSocket;
});
afterEach(() => { vi.restoreAllMocks(); });

const SESSION = "sess-abc";
const MSG_ID = "msg-123";

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0, staleTime: 0 } } });
  qc.setQueryData(["play-messages", SESSION], []);
  return { qc, wrapper: ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  ) };
}

async function openWs() {
  await act(async () => { FakeWebSocket.constructed[0]?.simulateOpen(); });
}

describe("useChatSession — tool_call / tool_result (Phase 2B)", () => {
  it("tool_call frame appends a pending ToolCall entry", async () => {
    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useChatSession({ sessionId: SESSION }), { wrapper });
    await openWs();

    act(() => result.current.send("hi"));
    await act(async () => {
      FakeWebSocket.constructed[0].simulateFrame({ type: "start", message_id: MSG_ID });
      FakeWebSocket.constructed[0].simulateFrame({
        type: "tool_call", message_id: MSG_ID, id: "tc-1",
        name: "neo4j_search", args: { q: "Geralt" },
      });
    });

    expect(result.current.streamingMsg?.toolCalls).toEqual([
      { id: "tc-1", name: "neo4j_search", args: { q: "Geralt" }, pending: true },
    ]);
  });

  it("tool_result resolves the matching entry with result_preview", async () => {
    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useChatSession({ sessionId: SESSION }), { wrapper });
    await openWs();

    act(() => result.current.send("hi"));
    await act(async () => {
      FakeWebSocket.constructed[0].simulateFrame({ type: "start", message_id: MSG_ID });
      FakeWebSocket.constructed[0].simulateFrame({
        type: "tool_call", message_id: MSG_ID, id: "tc-1",
        name: "mongo_query", args: { collection: "scenes" },
      });
      FakeWebSocket.constructed[0].simulateFrame({
        type: "tool_result", message_id: MSG_ID, tool_call_id: "tc-1",
        name: "mongo_query", result_preview: "[{...}, {...}]",
      });
    });

    expect(result.current.streamingMsg?.toolCalls?.[0]?.pending).toBe(false);
    expect(result.current.streamingMsg?.toolCalls?.[0]?.result_preview).toBe("[{...}, {...}]");
  });

  it("tool_result with error marks the entry as failed", async () => {
    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useChatSession({ sessionId: SESSION }), { wrapper });
    await openWs();

    act(() => result.current.send("hi"));
    await act(async () => {
      FakeWebSocket.constructed[0].simulateFrame({ type: "start", message_id: MSG_ID });
      FakeWebSocket.constructed[0].simulateFrame({
        type: "tool_call", message_id: MSG_ID, id: "tc-err", name: "qdrant_search",
      });
      FakeWebSocket.constructed[0].simulateFrame({
        type: "tool_result", message_id: MSG_ID, tool_call_id: "tc-err",
        name: "qdrant_search", error: "ConnectionRefused",
      });
    });

    expect(result.current.streamingMsg?.toolCalls?.[0]?.error).toBe("ConnectionRefused");
    expect(result.current.streamingMsg?.toolCalls?.[0]?.pending).toBe(false);
  });
});
