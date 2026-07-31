// @vitest-environment happy-dom
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { WorldContextProvider } from "@/lib/world-context";
import { entitiesApi, gmApi, universesApi } from "@/lib/api";
import type { RPGSystem, Universe } from "@/lib/types";
import GMAssistantPage from "./page";

// The page reads ?universe= deep links; tests always run without one.
vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(),
}));

const SERVER_ROLL = {
  total: 18,
  rolls: [15],
  expression: "1d20+3",
  kept_rolls: [15],
  modifier: 3,
};

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <WorldContextProvider>
        <GMAssistantPage />
      </WorldContextProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.restoreAllMocks();
  // Stub fetch — happy-dom's would hit a real backend.
  globalThis.fetch = vi.fn(() =>
    Promise.resolve(new Response("[]", { status: 200, headers: { "Content-Type": "application/json" } })),
  ) as unknown as typeof fetch;
});

describe("GM Assistant dice roller (server-authoritative)", () => {
  it("calls gmApi.rollDice with the expression and renders server values", async () => {
    const spy = vi.spyOn(gmApi, "rollDice").mockResolvedValue(SERVER_ROLL);
    const user = userEvent.setup();
    renderPage();

    const input = screen.getByPlaceholderText("e.g. 2d6+3");
    await user.clear(input);
    await user.type(input, "1d20+3");
    await user.keyboard("{Enter}");

    await waitFor(() => expect(spy).toHaveBeenCalledWith("1d20+3"));
    // History entry is built from the SERVER response, not a client roll.
    expect(await screen.findByText("18")).toBeInTheDocument();
    expect(screen.getByText("[15] +3")).toBeInTheDocument();
  });

  it("disables rolling for invalid expressions and never calls the API", async () => {
    const spy = vi.spyOn(gmApi, "rollDice").mockResolvedValue(SERVER_ROLL);
    const user = userEvent.setup();
    renderPage();

    const input = screen.getByPlaceholderText("e.g. 2d6+3");
    await user.clear(input);
    await user.type(input, "garbage");

    const rollButton = input.parentElement!.querySelector("button")!;
    expect(rollButton).toBeDisabled();
    await user.keyboard("{Enter}");
    expect(spy).not.toHaveBeenCalled();
    expect(screen.getByText("No rolls yet")).toBeInTheDocument();
  });

  it("routes quick-dice buttons through the server roll", async () => {
    const spy = vi.spyOn(gmApi, "rollDice").mockResolvedValue({
      total: 4,
      rolls: [4],
      expression: "1d6",
      kept_rolls: [4],
      modifier: 0,
    });
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByText("d6"));

    await waitFor(() => expect(spy).toHaveBeenCalledWith("1d6"));
    expect(await screen.findByText("4")).toBeInTheDocument();
    expect(screen.getByText("[4]")).toBeInTheDocument();
  });
});

function makeSystem(id: string, name: string): RPGSystem {
  return {
    id,
    name,
    description: null,
    version: null,
    core_mechanic: {
      mechanic_type: "dice",
      formula: `${name} formula`,
      success_type: null,
      target_number: null,
      description: null,
    },
    attributes: [],
    skills: [],
    resources: [],
    rules: [],
    is_builtin: false,
    source_document_id: null,
    character_count: 0,
    session_count: 0,
    needs_review: false,
    degenerate_reason: null,
  };
}

function makeUniverse(id: string, name: string, systemId: string | null): Universe {
  return {
    id,
    name,
    multiverse_id: "mv-1",
    genre: null,
    description: null,
    default_game_system_id: systemId,
    tags: [],
    is_active: false,
    entity_count: 0,
    session_count: 0,
    created_at: "2026-01-01T00:00:00Z",
  };
}

function mockUniverseApis(universes: Universe[], systems: RPGSystem[]) {
  vi.spyOn(universesApi, "listMultiverses").mockResolvedValue([]);
  vi.spyOn(universesApi, "listUniverses").mockResolvedValue(universes);
  const getUniverseSpy = vi
    .spyOn(universesApi, "getUniverse")
    .mockImplementation(async (id) => universes.find((u) => u.id === id)!);
  vi.spyOn(entitiesApi, "listSystems").mockResolvedValue(systems);
  const getSystemSpy = vi
    .spyOn(entitiesApi, "getSystem")
    .mockImplementation(async (id) => systems.find((s) => s.id === id)!);
  return { getUniverseSpy, getSystemSpy };
}

describe("GM Assistant rules panel (universe-aware, P2.2)", () => {
  it("populates the rules panel from the selected universe's bound system", async () => {
    const universes = [makeUniverse("u-1", "Alpha World", "sys-1")];
    const systems = [makeSystem("sys-1", "Bound System")];
    const { getSystemSpy } = mockUniverseApis(universes, systems);
    const user = userEvent.setup();
    renderPage();

    const universeSelect = (await screen.findByText("Alpha World")).closest("select")!;
    await user.selectOptions(universeSelect, "u-1");

    // The rules panel fetches and renders the bound system without any
    // manual dropdown selection.
    await waitFor(() => expect(getSystemSpy).toHaveBeenCalledWith("sys-1"));
    expect(await screen.findByText("Bound System formula")).toBeInTheDocument();
    // The system dropdown reflects the bound system too.
    expect(screen.getByDisplayValue("Bound System")).toBeInTheDocument();
  });

  it("keeps a manual system choice when the universe is re-selected", async () => {
    const universes = [
      makeUniverse("u-1", "Alpha World", "sys-1"),
      makeUniverse("u-2", "Beta World", "sys-1"),
    ];
    const systems = [makeSystem("sys-1", "Bound System"), makeSystem("sys-2", "Manual System")];
    const { getUniverseSpy, getSystemSpy } = mockUniverseApis(universes, systems);
    const user = userEvent.setup();
    renderPage();

    // Select a universe → its bound system populates.
    const universeSelect = (await screen.findByText("Alpha World")).closest("select")!;
    await user.selectOptions(universeSelect, "u-1");
    const systemSelect = await screen.findByDisplayValue("Bound System");

    // The GM overrides the system by hand.
    await user.selectOptions(systemSelect, "sys-2");
    await screen.findByDisplayValue("Manual System");
    const callsBeforeReselect = getSystemSpy.mock.calls.length;

    // Re-selecting a universe must not clobber the manual choice.
    await user.selectOptions(universeSelect, "u-2");
    await waitFor(() => expect(getUniverseSpy).toHaveBeenCalledWith("u-2"));
    // Give the universe-detail query and the auto-effect time to settle.
    await waitFor(() =>
      expect(screen.getByDisplayValue("Manual System")).toBeInTheDocument(),
    );
    await new Promise((r) => setTimeout(r, 50));

    expect(screen.getByDisplayValue("Manual System")).toBeInTheDocument();
    // No new system fetch: systemId never moved off the manual choice.
    expect(getSystemSpy.mock.calls.length).toBe(callsBeforeReselect);
  });
});

describe("GM Assistant scratchpad (P2.3 — server-backed, no localStorage)", () => {
  it("hydrates notes from the API and autosaves debounced edits via the API", async () => {
    mockUniverseApis([makeUniverse("u-1", "Alpha World", "sys-1")], [makeSystem("sys-1", "Bound")]);
    const getSpy = vi.spyOn(gmApi, "getNotes").mockResolvedValue({
      universe_id: "u-1",
      content: "the party crossed the river",
      updated_at: "2026-07-23T10:00:00Z",
    });
    const upsertSpy = vi.spyOn(gmApi, "upsertNotes").mockResolvedValue({
      universe_id: "u-1",
      content: "",
      updated_at: "2026-07-23T10:01:00Z",
    });
    const setItemSpy = vi.spyOn(Storage.prototype, "setItem");

    const user = userEvent.setup();
    renderPage();

    // Pick a universe so the notebook is enabled.
    const universeSelect = (await screen.findByText("Alpha World")).closest("select")!;
    await user.selectOptions(universeSelect, "u-1");

    // Switch to the Scratchpad tab. The page renders two "Scratchpad" tabs
    // (mobile tab bar + desktop center tabs, both visible under happy-dom);
    // click the desktop center-tab one, which is last in DOM order.
    const scratchpadTabs = screen.getAllByRole("button", { name: /scratchpad/i });
    await user.click(scratchpadTabs[scratchpadTabs.length - 1]);

    // The notebook fetches existing content from the API.
    await waitFor(() => expect(getSpy).toHaveBeenCalledWith("u-1"));
    const textarea = (await screen.findByPlaceholderText(
      /Record events, NPC dialogue/i,
    )) as HTMLTextAreaElement;
    await waitFor(() => expect(textarea.value).toBe("the party crossed the river"));

    // Type — debounced (1.5s) autosave fires.
    await user.click(textarea);
    await user.keyboard(" and found the chapel");
    await waitFor(
      () => expect(upsertSpy).toHaveBeenCalled(),
      { timeout: 3000 },
    );
    expect(upsertSpy).toHaveBeenCalledWith("u-1", "the party crossed the river and found the chapel");

    // localStorage must not be touched — the notebook is server-backed now.
    expect(setItemSpy).not.toHaveBeenCalledWith("gm-notebook-u-1", expect.anything());
  });
});


describe("GM Assistant hidden tool panels (user-modifiable prefs)", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("shows a placeholder instead of a hidden panel when every tool panel is hidden", () => {
    window.localStorage.setItem(
      "monitor.gm.hiddenPanels",
      JSON.stringify(["ask-world", "hooks", "threads", "contradictions", "session-prep", "handouts"]),
    );
    renderPage();

    expect(screen.getByText(/all panels hidden — customize to re-enable/i)).toBeInTheDocument();
    // No tool panel body leaks through — not even the ask-the-world default.
    expect(screen.queryByPlaceholderText(/ask the world/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/select a universe to generate plot hooks/i)).not.toBeInTheDocument();
  });

  it("falls back to the first visible panel rather than a hidden ask-world", () => {
    window.localStorage.setItem("monitor.gm.hiddenPanels", JSON.stringify(["ask-world"]));
    renderPage();

    // The default active panel is the recorder (a non-tool panel), so the tools
    // body falls back to the first VISIBLE tool panel — Hooks — never the
    // hidden Ask panel.
    expect(screen.getByText(/select a universe to generate plot hooks/i)).toBeInTheDocument();
    expect(screen.queryByPlaceholderText(/ask the world/i)).not.toBeInTheDocument();
  });
});
