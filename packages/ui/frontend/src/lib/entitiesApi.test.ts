import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { entitiesApi } from "./api";

// The entity CRUD helpers (M-36 / M-38) just shape the request — assert the
// method, path and JSON body the UI sends to the backend.

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

describe("entitiesApi CRUD payloads", () => {
  beforeEach(() => mockFetch({ id: "e1", name: "Mira" }));
  afterEach(() => vi.unstubAllGlobals());

  it("getEntity issues GET to the doubled entities path", async () => {
    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
    await entitiesApi.getEntity("e1");
    const { url, init } = lastCall(fetchMock);
    expect(url).toContain("/api/entities/entities/e1");
    expect(init.method ?? "GET").toBe("GET");
  });

  it("createEntity POSTs the entity payload", async () => {
    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
    await entitiesApi.createEntity({
      universe_id: "u1",
      name: "Iron Brotherhood",
      entity_type: "faction",
      description: "A mercenary order.",
    });
    const { url, init } = lastCall(fetchMock);
    expect(url).toContain("/api/entities/entities");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({
      universe_id: "u1",
      name: "Iron Brotherhood",
      entity_type: "faction",
      description: "A mercenary order.",
    });
  });

  it("updateEntity PATCHes only the supplied fields incl. tags", async () => {
    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
    await entitiesApi.updateEntity("e1", {
      description: "A grizzled veteran.",
      tags: ["wounded", "hidden"],
    });
    const { url, init } = lastCall(fetchMock);
    expect(url).toContain("/api/entities/entities/e1");
    expect(init.method).toBe("PATCH");
    expect(JSON.parse(init.body as string)).toEqual({
      description: "A grizzled veteran.",
      tags: ["wounded", "hidden"],
    });
  });

  it("createRelationship POSTs to the edges endpoint (M-37)", async () => {
    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
    await entitiesApi.createRelationship({
      from_id: "a",
      to_id: "b",
      rel_type: "MEMBER_OF",
    });
    const { url, init } = lastCall(fetchMock);
    expect(url).toContain("/api/entities/entities/edges");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({
      from_id: "a",
      to_id: "b",
      rel_type: "MEMBER_OF",
    });
  });

  it("listRelationships GETs an entity's edges (M-37)", async () => {
    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
    await entitiesApi.listRelationships("a");
    const { url, init } = lastCall(fetchMock);
    expect(url).toContain("/api/entities/entities/a/edges");
    expect(init.method ?? "GET").toBe("GET");
  });
});
