// @vitest-environment happy-dom
import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { usePlaySession } from "./usePlaySession";
import { WorldContextProvider } from "@/lib/world-context";
import type { Session } from "@/lib/types";

vi.mock("@/lib/api", () => ({
  chatApi: {
    listSessions: vi.fn(),
    listBenchmarks: vi.fn(async () => []),
    getSessionState: vi.fn(async () => ({})),
    createSession: vi.fn(),
    deleteSession: vi.fn(),
    patchSession: vi.fn(),
    skipPreplay: vi.fn(),
    beginStory: vi.fn(),
  },
}));

import { chatApi } from "@/lib/api";

const s1 = { id: "s-1", title: "First", mode: "autonomous_gm" } as Session;
const s2 = { id: "s-2", title: "Deep link", mode: "autonomous_gm" } as Session;
const architect = { id: "s-a", title: "World", mode: "world_architect" } as Session;

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>
      <WorldContextProvider>{children}</WorldContextProvider>
    </QueryClientProvider>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(chatApi.listSessions).mockResolvedValue([architect, s1, s2]);
});

describe("usePlaySession", () => {
  it("auto-selects the first non-architect session", async () => {
    const { result } = renderHook(() => usePlaySession({ requestedSessionId: null }), {
      wrapper: makeWrapper(),
    });
    await waitFor(() => expect(result.current.activeSessionId).toBe("s-1"));
    expect(result.current.sessions.map((s) => s.id)).toEqual(["s-1", "s-2"]);
    expect(result.current.activeSession?.title).toBe("First");
  });

  it("honours a deep-linked session id and notifies the caller", async () => {
    const onDeepLinkSelected = vi.fn();
    const { result } = renderHook(
      () => usePlaySession({ requestedSessionId: "s-2", onDeepLinkSelected }),
      { wrapper: makeWrapper() },
    );
    await waitFor(() => expect(result.current.activeSessionId).toBe("s-2"));
    expect(onDeepLinkSelected).toHaveBeenCalled();
  });

  it("activates a newly created session", async () => {
    vi.mocked(chatApi.createSession).mockResolvedValue({ ...s1, id: "s-new" } as Session);
    const onSessionCreated = vi.fn();
    const { result } = renderHook(
      () => usePlaySession({ requestedSessionId: null, onSessionCreated }),
      { wrapper: makeWrapper() },
    );
    await waitFor(() => expect(result.current.activeSessionId).toBe("s-1"));

    act(() => {
      result.current.createSession.mutate({ title: "New" } as never);
    });
    await waitFor(() => expect(result.current.activeSessionId).toBe("s-new"));
    expect(onSessionCreated).toHaveBeenCalled();
  });
});
