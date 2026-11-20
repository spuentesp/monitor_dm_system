// @vitest-environment happy-dom
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { usePlaySocket } from "./usePlaySocket";
import { useChatSession } from "@/features/chat";

vi.mock("@/features/chat", () => ({
  useChatSession: vi.fn(),
}));

interface FakeChat {
  status: string;
  isTyping: boolean;
  streamingMsg: { id: string; text: string } | null;
  stop: ReturnType<typeof vi.fn>;
}

function setChat(chat: Partial<FakeChat>) {
  vi.mocked(useChatSession).mockReturnValue({
    status: "connected",
    isTyping: false,
    streamingMsg: null,
    stop: vi.fn(),
    ...chat,
  } as never);
}

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
}

beforeEach(() => {
  vi.useFakeTimers();
  setChat({});
});

afterEach(() => {
  vi.useRealTimers();
});

describe("usePlaySocket", () => {
  it("reports no active turn while idle", () => {
    const { result } = renderHook(() => usePlaySocket({ sessionId: "s-1" }), {
      wrapper: makeWrapper(),
    });
    expect(result.current.turnActive).toBe(false);
    expect(result.current.isWaitingForGm).toBe(false);
    expect(result.current.waitedSeconds).toBe(0);
    expect(result.current.isConnectionLost).toBe(false);
  });

  it("tracks the GM-thinking wait with elapsed seconds", () => {
    setChat({ isTyping: true });
    const { result, rerender } = renderHook(() => usePlaySocket({ sessionId: "s-1" }), {
      wrapper: makeWrapper(),
    });
    expect(result.current.turnActive).toBe(true);
    expect(result.current.isWaitingForGm).toBe(true);

    act(() => {
      vi.advanceTimersByTime(2500);
    });
    expect(result.current.waitedSeconds).toBe(2);

    // Tokens start flowing → no longer "thinking", still waiting overall.
    setChat({ isTyping: false, streamingMsg: { id: "m1", text: "Hel" } });
    rerender();
    expect(result.current.turnActive).toBe(true);
    expect(result.current.isWaitingForGm).toBe(false);
  });

  it("resets the timer when the turn settles", () => {
    setChat({ isTyping: true });
    const { result, rerender } = renderHook(() => usePlaySocket({ sessionId: "s-1" }), {
      wrapper: makeWrapper(),
    });
    act(() => {
      vi.advanceTimersByTime(3000);
    });
    expect(result.current.waitedSeconds).toBe(3);

    setChat({ isTyping: false, streamingMsg: null });
    rerender();
    expect(result.current.turnActive).toBe(false);
    expect(result.current.waitedSeconds).toBe(0);
  });

  it("cancelTurn stops the underlying chat session and clears the wait", () => {
    const stop = vi.fn();
    setChat({ isTyping: true, stop });
    const { result } = renderHook(() => usePlaySocket({ sessionId: "s-1" }), {
      wrapper: makeWrapper(),
    });
    act(() => {
      vi.advanceTimersByTime(1000);
    });
    act(() => {
      result.current.cancelTurn();
    });
    expect(stop).toHaveBeenCalledTimes(1);
    expect(result.current.waitedSeconds).toBe(0);
  });

  it("surfaces a lost connection while the socket reconnects", () => {
    setChat({ status: "reconnecting" });
    const { result } = renderHook(() => usePlaySocket({ sessionId: "s-1" }), {
      wrapper: makeWrapper(),
    });
    expect(result.current.status).toBe("reconnecting");
    expect(result.current.isConnectionLost).toBe(true);
  });
});
