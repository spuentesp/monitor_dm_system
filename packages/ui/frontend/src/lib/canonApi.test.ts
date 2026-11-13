import { afterEach, describe, expect, it, vi } from "vitest";
import { canonApi } from "./api";

describe("canon review requests", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("sends the override reason as a distinct query parameter", async () => {
    const fetchMock = vi.fn(async (_url: RequestInfo | URL, _init?: RequestInit) => new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    await canonApi.acceptProposal("p1", "Confirmed", "The story changed");
    const url = new URL(String(fetchMock.mock.calls[0][0]), "http://localhost");
    expect(url.searchParams.get("reason")).toBe("Confirmed");
    expect(url.searchParams.get("override_reason")).toBe("The story changed");
  });
});
