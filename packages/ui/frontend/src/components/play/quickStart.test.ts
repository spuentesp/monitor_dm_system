import { describe, it, expect, vi, beforeEach } from "vitest";
import { buildQuickStartPayload, createQuickStartSession } from "./quickStart";

vi.mock("@/lib/api", () => ({
  chatApi: { createSession: vi.fn() },
  entitiesApi: { listSystems: vi.fn() },
  universesApi: { listUniverses: vi.fn() },
}));

import { chatApi, entitiesApi, universesApi } from "@/lib/api";

const universe = {
  id: "u-1",
  name: "Mistlands",
  multiverse_id: "m-1",
} as never;

const system = { id: "sys-1", name: "D20 Freeform" } as never;

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(universesApi.listUniverses).mockResolvedValue([universe]);
  vi.mocked(entitiesApi.listSystems).mockResolvedValue([system]);
  vi.mocked(chatApi.createSession).mockResolvedValue({ id: "s-1" } as never);
});

describe("buildQuickStartPayload", () => {
  it("picks the first universe/system with SetupPanel defaults", async () => {
    const payload = await buildQuickStartPayload();
    expect(payload).toMatchObject({
      title: "New Mistlands campaign",
      mode: "autonomous_gm",
      tone: "dramatic",
      play_mode: "narrative",
      multiverse_id: "m-1",
      universe_id: "u-1",
      universe_label: "Mistlands",
      system_id: "sys-1",
      system_label: "D20 Freeform",
    });
  });

  it("throws when there is no universe to bind to", async () => {
    vi.mocked(universesApi.listUniverses).mockResolvedValue([]);
    await expect(buildQuickStartPayload()).rejects.toThrow(/no worlds yet/i);
  });

  it("still builds a payload when the system catalog fails", async () => {
    vi.mocked(entitiesApi.listSystems).mockRejectedValue(new Error("down"));
    const payload = await buildQuickStartPayload();
    expect(payload.system_id).toBeNull();
    expect(payload.system_label).toBeNull();
  });
});

describe("createQuickStartSession", () => {
  it("creates the session through chatApi", async () => {
    const session = await createQuickStartSession();
    expect(session).toEqual({ id: "s-1" });
    expect(chatApi.createSession).toHaveBeenCalledWith(
      expect.objectContaining({ universe_id: "u-1" }),
    );
  });
});
