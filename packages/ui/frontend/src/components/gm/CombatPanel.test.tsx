// @vitest-environment happy-dom
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { gmApi, storiesApi } from "@/lib/api";
import { gmCombatApi } from "@/lib/gm-combat-api";
import type { CombatSessionState } from "@/lib/gm-combat-api";
import { CombatPanel } from "./CombatPanel";

function renderPanel(universeId: string | null, systemId?: string | null) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <CombatPanel universeId={universeId} systemId={systemId ?? null} />
    </QueryClientProvider>,
  );
}

function makeState(over: Partial<CombatSessionState> = {}): CombatSessionState {
  return {
    universe_id: "u-1",
    session_id: "s-1",
    status: "active",
    round: 1,
    turn_order: [],
    combatants: [
      {
        id: "c-1",
        name: "Mira",
        side: "pc",
        hp: 24,
        max_hp: 24,
        temp_hp: 0,
        initiative: null,
        conditions: [],
        dead: false,
        unconscious: false,
        concentration: null,
        notes: "",
        entity_id: null,
      },
      {
        id: "c-2",
        name: "Goblin",
        side: "enemy",
        hp: 7,
        max_hp: 7,
        temp_hp: 0,
        initiative: null,
        conditions: [],
        dead: false,
        unconscious: false,
        concentration: null,
        notes: "",
        entity_id: null,
      },
    ],
    story_id: null,
    scene_id: null,
    started_at: "2026-11-11T12:00:00Z",
    ended_at: null,
    ...over,
  };
}

beforeEach(() => {
  vi.restoreAllMocks();
  localStorage.clear();
  globalThis.fetch = vi.fn(() =>
    Promise.resolve(new Response("[]", { status: 200, headers: { "Content-Type": "application/json" } })),
  ) as unknown as typeof fetch;
  vi.spyOn(storiesApi, "listStories").mockResolvedValue({ stories: [], total: 0 });
});

describe("CombatPanel (CF-9)", () => {
  it("prompts for a universe when none is selected", () => {
    renderPanel(null);
    expect(screen.getByText(/select a universe to run an encounter/i)).toBeInTheDocument();
  });

  it("starts an encounter from the draft rows and renders the tracker", async () => {
    const startSpy = vi.spyOn(gmCombatApi, "start").mockResolvedValue(makeState());
    vi.spyOn(gmCombatApi, "get").mockResolvedValue(makeState());
    const user = userEvent.setup();
    renderPanel("u-1");

    expect(await screen.findByText(/new encounter/i)).toBeInTheDocument();
    const [name, hp, max] = screen.getAllByPlaceholderText(/name|hp|max/i);
    await user.type(name, "Mira");
    await user.selectOptions(screen.getByDisplayValue("Enemy"), "pc");
    await user.type(hp, "24");
    await user.type(max, "24");
    await user.click(screen.getByRole("button", { name: /start/i }));

    await waitFor(() =>
      expect(startSpy).toHaveBeenCalledWith(
        expect.objectContaining({
          universe_id: "u-1",
          combatants: [{ name: "Mira", side: "pc", hp: 24, max_hp: 24 }],
        }),
      ),
    );
    // Tracker view: round header + both combatants (each appears in the
    // initiative editor and the combatant card).
    expect(await screen.findByText(/round 1/i)).toBeInTheDocument();
    expect(screen.getAllByText("Mira").length).toBeGreaterThanOrEqual(2);
    expect(screen.getAllByText("Goblin").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText("24/24")).toBeInTheDocument();
    expect(screen.getByText("7/7")).toBeInTheDocument();
  });

  it("shows the no-encounter start view after a 404 on GET", async () => {
    const { ApiError } = await import("@/lib/api");
    vi.spyOn(gmCombatApi, "get").mockRejectedValue(new ApiError(404, "Not found"));
    renderPanel("u-1");

    expect(await screen.findByText(/new encounter/i)).toBeInTheDocument();
  });

  it("loads a live encounter from the stored session and sets initiative", async () => {
    localStorage.setItem("monitor.gm.combatSession:u-1", "s-1");
    const state = makeState();
    vi.spyOn(gmCombatApi, "get").mockResolvedValue(state);
    const setSpy = vi.spyOn(gmCombatApi, "setInitiative").mockResolvedValue({
      state: {
        ...state,
        status: "active",
        turn_order: ["c-2", "c-1"],
        combatants: [
          { ...state.combatants[1], initiative: 18 },
          { ...state.combatants[0], initiative: 12 },
        ],
      },
      narration: "The Goblin acts first!",
    });
    const user = userEvent.setup();
    renderPanel("u-1");

    expect(await screen.findByText(/round 1/i)).toBeInTheDocument();

    // Enter initiative for both combatants and set the order.
    await user.type(screen.getByLabelText("Initiative for Mira"), "12");
    await user.type(screen.getByLabelText("Initiative for Goblin"), "18");
    await user.click(screen.getByRole("button", { name: /set order/i }));

    await waitFor(() =>
      expect(setSpy).toHaveBeenCalledWith(
        "s-1",
        expect.objectContaining({
          universe_id: "u-1",
          entries: [
            { combatant_id: "c-1", initiative: 12 },
            { combatant_id: "c-2", initiative: 18 },
          ],
        }),
      ),
    );
    // Narration surfaces when requested by the server response.
    expect(await screen.findByText("The Goblin acts first!")).toBeInTheDocument();
  });

  it("applies damage through the server roll then PATCHes hp_delta", async () => {
    localStorage.setItem("monitor.gm.combatSession:u-1", "s-1");
    const state = makeState();
    vi.spyOn(gmCombatApi, "get").mockResolvedValue(state);
    const rollSpy = vi.spyOn(gmApi, "rollDice").mockResolvedValue({
      total: 9,
      rolls: [6],
      expression: "1d6+3",
      kept_rolls: [6],
      modifier: 3,
    });
    const patchSpy = vi
      .spyOn(gmCombatApi, "updateCombatant")
      .mockResolvedValue({ ...state, round: 1 });
    const user = userEvent.setup();
    renderPanel("u-1");

    expect(await screen.findByText(/round 1/i)).toBeInTheDocument();
    // The combatant card header (not the initiative-editor row) owns the Dmg button.
    const goblinHeader = screen
      .getAllByText("Goblin")
      .find((el) => el.className.includes("font-semibold"))!;
    const goblinRow = goblinHeader.closest("div[class*='glass-dark']")!;
    const dmgInput = goblinRow.querySelector(
      "input[aria-label^='Damage or heal amount for Goblin']",
    ) as HTMLInputElement;
    expect(dmgInput).toBeTruthy();
    await user.type(dmgInput, "1d6+3");
    const dmgButton = Array.from(goblinRow.querySelectorAll("button")).find(
      (b) => b.textContent?.trim() === "Dmg",
    )!;
    await user.click(dmgButton);

    await waitFor(() => expect(rollSpy).toHaveBeenCalledWith("1d6+3"));
    await waitFor(() =>
      expect(patchSpy).toHaveBeenCalledWith(
        "s-1",
        "c-2",
        expect.objectContaining({ universe_id: "u-1", hp_delta: -9 }),
      ),
    );
  });

  it("ends the encounter with world effects and shows staged proposals", async () => {
    localStorage.setItem("monitor.gm.combatSession:u-1", "s-1");
    const state = makeState();
    vi.spyOn(gmCombatApi, "get").mockResolvedValue(state);
    const endSpy = vi.spyOn(gmCombatApi, "end").mockResolvedValue({
      state: { ...state, status: "resolved", ended_at: "2026-11-11T13:00:00Z" },
      proposal_ids: ["p-1", "p-2"],
      proposal_errors: [],
      summary: "Two rounds; the Goblin fell.",
    });
    const user = userEvent.setup();
    renderPanel("u-1");

    expect(await screen.findByText(/round 1/i)).toBeInTheDocument();
    await user.type(
      screen.getByPlaceholderText(/goblin warband/i),
      "The goblin warband swears vengeance",
    );
    await user.click(screen.getByRole("button", { name: /end/i }));

    await waitFor(() =>
      expect(endSpy).toHaveBeenCalledWith(
        "s-1",
        expect.objectContaining({
          universe_id: "u-1",
          world_effects: ["The goblin warband swears vengeance"],
        }),
      ),
    );
    expect(await screen.findByText(/encounter ended/i)).toBeInTheDocument();
    expect(screen.getByText(/two rounds; the goblin fell/i)).toBeInTheDocument();
    expect(screen.getByText(/2 proposal\(s\) staged/i)).toBeInTheDocument();
    // Resolved view hides the round/end controls.
    expect(screen.queryByRole("button", { name: /round/i })).not.toBeInTheDocument();
  });

  it("explains a condition tag via the condition-explain endpoint", async () => {
    localStorage.setItem("monitor.gm.combatSession:u-1", "s-1");
    const state = makeState({
      combatants: [
        {
          ...makeState().combatants[0],
          conditions: ["poisoned"],
        },
        makeState().combatants[1],
      ],
    });
    vi.spyOn(gmCombatApi, "get").mockResolvedValue(state);
    const explainSpy = vi.spyOn(gmCombatApi, "explainCondition").mockResolvedValue({
      condition: "poisoned",
      source: "system",
      description: "-2 to attacks; lose 5 HP at dawn",
      mechanical_effects: ["-2 to attacks"],
      ends_when: "a successful Constitution save",
    });
    const user = userEvent.setup();
    renderPanel("u-1", "sys-1");

    expect(await screen.findByText(/round 1/i)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /^poisoned$/i }));

    await waitFor(() =>
      expect(explainSpy).toHaveBeenCalledWith(
        expect.objectContaining({ universe_id: "u-1", condition: "poisoned", system_id: "sys-1" }),
      ),
    );
    expect(await screen.findByText(/-2 to attacks/i)).toBeInTheDocument();
    expect(screen.getByText(/ends: a successful constitution save/i)).toBeInTheDocument();
  });

  it("advances the round via next-round", async () => {
    localStorage.setItem("monitor.gm.combatSession:u-1", "s-1");
    const state = makeState();
    vi.spyOn(gmCombatApi, "get").mockResolvedValue(state);
    const nextSpy = vi
      .spyOn(gmCombatApi, "nextRound")
      .mockResolvedValue({ ...state, round: 2 });
    const user = userEvent.setup();
    renderPanel("u-1");

    expect(await screen.findByText(/round 1/i)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /round/i }));

    await waitFor(() => expect(nextSpy).toHaveBeenCalledWith("s-1", "u-1"));
    expect(await screen.findByText(/round 2/i)).toBeInTheDocument();
  });
});
