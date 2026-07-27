import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { entitiesApi } from "./api";

// The conversatory helpers just shape the request — assert method, path and
// JSON body the UI sends to the backend.

function mockFetch(body: unknown) {
  const fetchMock = vi.fn(async () =>
    new Response(JSON.stringify(body), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }),
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function lastCall(fetchMock: ReturnType<typeof vi.fn>) {
  const [url, init] = fetchMock.mock.calls.at(-1)!;
  return { url: String(url), init: init as RequestInit };
}

describe("character conversatory API payloads", () => {
  beforeEach(() => mockFetch({ conversation_id: "c1", opening: "hi" }));
  afterEach(() => vi.unstubAllGlobals());

  it("expandCharacter POSTs to the expand path", async () => {
    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
    await entitiesApi.expandCharacter("char-1");
    const { url, init } = lastCall(fetchMock);
    expect(url).toContain("/api/entities/characters/char-1/expand");
    expect(init.method).toBe("POST");
  });

  it("startCharacterConversation POSTs to the conversations path", async () => {
    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
    await entitiesApi.startCharacterConversation("char-1");
    const { url, init } = lastCall(fetchMock);
    expect(url).toContain("/api/entities/characters/char-1/conversations");
    expect(init.method).toBe("POST");
  });

  it("sendCharacterMessage POSTs the text body to the send path", async () => {
    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
    await entitiesApi.sendCharacterMessage("char-1", "conv-9", "Evening.");
    const { url, init } = lastCall(fetchMock);
    expect(url).toContain("/api/entities/characters/char-1/conversations/conv-9/send");
    expect(init.method).toBe("POST");
    // include_cross_incarnation is sent by default (false) — see
    // characterVersionsApi.test.ts for the explicit opt-in case.
    expect(JSON.parse(String(init.body))).toEqual({
      text: "Evening.",
      include_cross_incarnation: false,
    });
  });

  it("endCharacterConversation POSTs to the end path", async () => {
    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
    await entitiesApi.endCharacterConversation("char-1", "conv-9");
    const { url, init } = lastCall(fetchMock);
    expect(url).toContain("/api/entities/characters/char-1/conversations/conv-9/end");
    expect(init.method).toBe("POST");
  });

  it("listCharacterConversations GETs with a limit query", async () => {
    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
    await entitiesApi.listCharacterConversations("char-1", 5);
    const { url, init } = lastCall(fetchMock);
    expect(url).toContain("/api/entities/characters/char-1/conversations");
    expect(url).toContain("limit=5");
    expect(init.method ?? "GET").toBe("GET");
  });
});
