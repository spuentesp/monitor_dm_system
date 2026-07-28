import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { promptCollectionsApi } from "./api";

// promptCollectionsApi.list (P-19 / Session Zero curation) shapes the request
// — assert it preserves include_builtin as a real boolean, drops undefined,
// and keeps pagination/filter encoding intact.

function mockFetch() {
  const fetchMock = vi.fn(async () =>
    new Response(JSON.stringify({ items: [], total: 0, limit: 50, offset: 0 }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }),
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function lastUrl(fetchMock: ReturnType<typeof vi.fn>) {
  const [url] = fetchMock.mock.calls.at(-1)!;
  return String(url);
}

describe("promptCollectionsApi.list query serialization", () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = mockFetch();
  });
  afterEach(() => vi.unstubAllGlobals());

  it("serializes include_builtin=false as the literal string 'false'", async () => {
    await promptCollectionsApi.list({ include_builtin: false });
    expect(lastUrl(fetchMock)).toContain("include_builtin=false");
  });

  it("serializes include_builtin=true as the literal string 'true'", async () => {
    await promptCollectionsApi.list({ include_builtin: true });
    expect(lastUrl(fetchMock)).toContain("include_builtin=true");
  });

  it("omits include_builtin when undefined", async () => {
    await promptCollectionsApi.list({ category: "lore" });
    const url = lastUrl(fetchMock);
    expect(url).not.toContain("include_builtin");
    expect(url).toContain("category=lore");
  });

  it("preserves pagination and filter encoding", async () => {
    await promptCollectionsApi.list({
      category: "session zero",
      system_id: "sys-1",
      universe_id: "u-1",
      tag: "tactical",
      limit: 25,
      offset: 50,
    });
    const url = lastUrl(fetchMock);
    expect(url).toContain("category=session+zero");
    expect(url).toContain("system_id=sys-1");
    expect(url).toContain("universe_id=u-1");
    expect(url).toContain("tag=tactical");
    expect(url).toContain("limit=25");
    expect(url).toContain("offset=50");
    expect(url).not.toContain("include_builtin");
  });
});