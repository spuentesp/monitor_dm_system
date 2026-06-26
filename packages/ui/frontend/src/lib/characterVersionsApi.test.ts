import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { entitiesApi } from "./api";

// The character-versions API is a thin request-shaping layer. We assert the
// HTTP shape (method, path, body) the UI sends to the backend, mirroring
// entitiesApi.test.ts.

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

describe("character versions API payloads", () => {
  beforeEach(() => mockFetch({ version_id: "v1", entity_id: "e1", universe_id: "u1" }));
  afterEach(() => vi.unstubAllGlobals());

  it("listCharacterVersions GETs /versions", async () => {
    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
    await entitiesApi.listCharacterVersions("char-1");
    const { url, init } = lastCall(fetchMock);
    expect(url).toContain("/api/entities/characters/char-1/versions");
    expect(init.method ?? "GET").toBe("GET");
  });

  it("createCharacterVersion POSTs the universe_id body", async () => {
    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
    await entitiesApi.createCharacterVersion("char-1", { universe_id: "uni-A" });
    const { url, init } = lastCall(fetchMock);
    expect(url).toContain("/api/entities/characters/char-1/versions");
    expect(init.method).toBe("POST");
    expect(JSON.parse(String(init.body))).toEqual({ universe_id: "uni-A" });
  });

  it("deleteCharacterVersion DELETEs the per-universe path", async () => {
    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
    await entitiesApi.deleteCharacterVersion("char-1", "uni-A");
    const { url, init } = lastCall(fetchMock);
    expect(url).toContain("/api/entities/characters/char-1/versions/uni-A");
    expect(init.method).toBe("DELETE");
  });

  it("expandCharacter forwards optional universe_id body", async () => {
    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
    await entitiesApi.expandCharacter("char-1", { universe_id: "uni-A" });
    const { url, init } = lastCall(fetchMock);
    expect(url).toContain("/api/entities/characters/char-1/expand");
    expect(init.method).toBe("POST");
    expect(JSON.parse(String(init.body))).toEqual({ universe_id: "uni-A" });
  });

  it("expandCharacter sends no body when called without args", async () => {
    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
    await entitiesApi.expandCharacter("char-1");
    const { init } = lastCall(fetchMock);
    expect(init.method).toBe("POST");
    expect(init.body).toBeUndefined();
  });

  it("startCharacterConversation accepts universe_id", async () => {
    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
    await entitiesApi.startCharacterConversation("char-1", { universe_id: "uni-A" });
    const { url, init } = lastCall(fetchMock);
    expect(url).toContain("/api/entities/characters/char-1/conversations");
    expect(init.method).toBe("POST");
    expect(JSON.parse(String(init.body))).toEqual({ universe_id: "uni-A" });
  });

  it("startCharacterConversation sends empty body when called without args", async () => {
    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
    await entitiesApi.startCharacterConversation("char-1");
    const { init } = lastCall(fetchMock);
    expect(JSON.parse(String(init.body))).toEqual({});
  });

  it("sendCharacterMessage defaults include_cross_incarnation to false", async () => {
    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
    await entitiesApi.sendCharacterMessage("char-1", "conv-1", "hi");
    const { init } = lastCall(fetchMock);
    expect(JSON.parse(String(init.body))).toEqual({
      text: "hi",
      include_cross_incarnation: false,
    });
  });

  it("sendCharacterMessage forwards include_cross_incarnation=true", async () => {
    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
    await entitiesApi.sendCharacterMessage("char-1", "conv-1", "hi", {
      include_cross_incarnation: true,
    });
    const { init } = lastCall(fetchMock);
    expect(JSON.parse(String(init.body))).toEqual({
      text: "hi",
      include_cross_incarnation: true,
    });
  });
});
