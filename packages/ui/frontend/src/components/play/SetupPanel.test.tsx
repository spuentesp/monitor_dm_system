// @vitest-environment happy-dom
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { SetupPanel } from "./SetupPanel";
import { characterTemplatesApi, entitiesApi } from "@/lib/api";

const mockMultiverses = [{ id: "mv-1", name: "Mistlands" }];
const mockUniverses = [{ id: "u-1", name: "Mistlands — Canon" }];
// Empty by default: SetupPanel auto-selects the first system (once loaded)
// and then the first character for that system (once loaded) via its own
// pre-existing effects. An empty systems list keeps that auto-select from
// firing so tests 1/2 can isolate the persona picker; test 3 (which wants a
// Controlled PC selected) opts back in with its own per-test mock.
const mockSystems: Array<{ id: string; name: string }> = [];
const mockCharacters: Array<{ id: string; name: string }> = [];
const mockPersonas = [
  {
    id: "persona-1",
    name: "Rook",
    description: "A scavenger",
    avatar_url: null,
    personality: "Wary but loyal",
    gm_notes: "",
    first_message: "",
    is_ooc_persona: false,
    entity_id: null,
    default_universe_id: null,
    versions: [],
    memory_count: 0,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  },
];

const mockTemplates = [
  {
    template_id: "tpl-1",
    name: "Varys",
    concept: "A spymaster who is never where you expect",
    personality: "Charming, patient",
    backstory_beats: ["Lost a city to a bargain", "Never pays his debts"],
    voice: "Speaks in parables.",
    portrait_url: null,
    first_message: "",
    gm_notes: "",
    usage_count: 0,
  },
];

vi.mock("@/lib/api", () => ({
  universesApi: {
    listMultiverses: vi.fn(async () => mockMultiverses),
    listUniverses: vi.fn(async () => mockUniverses),
  },
  entitiesApi: {
    listSystems: vi.fn(async () => mockSystems),
    listCharacters: vi.fn(async () => mockCharacters),
    listStandaloneCharacters: vi.fn(async () => mockPersonas),
  },
  chatApi: {
    listBenchmarks: vi.fn(async () => []),
  },
  characterTemplatesApi: {
    remove: vi.fn(async () => undefined),
    list: vi.fn(async () => ({
      templates: mockTemplates,
      total: mockTemplates.length,
      limit: 100,
      offset: 0,
    })),
  },
}));

function renderPanel(onCreate = vi.fn()) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  render(<SetupPanel isPending={false} onCreate={onCreate} />, { wrapper });
  return onCreate;
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(entitiesApi.listSystems).mockResolvedValue(mockSystems);
  vi.mocked(entitiesApi.listCharacters).mockResolvedValue(mockCharacters);
  vi.mocked(entitiesApi.listStandaloneCharacters).mockResolvedValue(mockPersonas);
});

describe("SetupPanel persona picker", () => {
  it("clears the selection after deleting the selected template", async () => {
    const onCreate = renderPanel();
    await screen.findByRole("option", { name: "Varys (template)" });
    fireEvent.change(screen.getByLabelText(/play as a saved persona/i), { target: { value: "tpl-1" } });
    fireEvent.click(screen.getByRole("button", { name: "Edit selected template" }));
    fireEvent.click(screen.getByRole("button", { name: "Delete template" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm delete" }));
    await waitFor(() => expect(characterTemplatesApi.remove).toHaveBeenCalledWith("tpl-1"));
    await waitFor(() => expect(screen.getByLabelText(/play as a saved persona/i)).toHaveValue(""));
    fireEvent.click(screen.getByRole("button", { name: /create session/i }));
    expect(onCreate.mock.calls[0][0].persona_id).toBeNull();
  });
  it("lists saved personas and sends persona_id when one is selected", async () => {
    const onCreate = renderPanel();

    await waitFor(() => {
      expect(screen.getByText("Rook")).toBeInTheDocument();
    });

    fireEvent.change(screen.getByLabelText(/play as a saved persona/i), {
      target: { value: "persona-1" },
    });

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /create session/i })).not.toBeDisabled();
    });
    fireEvent.click(screen.getByRole("button", { name: /create session/i }));

    expect(onCreate).toHaveBeenCalledTimes(1);
    const payload = onCreate.mock.calls[0][0];
    expect(payload.persona_id).toBe("persona-1");
    expect(payload.character_id).toBeNull();
  });

  it("offers character templates and shows their voice and beat count", async () => {
    const onCreate = renderPanel();

    const select = await screen.findByLabelText(/play as a saved persona/i);
    await waitFor(() => {
      expect(screen.getByRole("option", { name: /Varys \(template\)/ })).toBeInTheDocument();
    });

    fireEvent.change(select, { target: { value: "tpl-1" } });

    const summary = await screen.findByTestId("persona-template-summary");
    expect(summary).toHaveTextContent("Voice: Speaks in parables.");
    expect(summary).toHaveTextContent("2 backstory beats");

    // A template seeds Session Zero exactly like a persona does.
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /create session/i })).not.toBeDisabled();
    });
    fireEvent.click(screen.getByRole("button", { name: /create session/i }));
    expect(onCreate.mock.calls[0][0].persona_id).toBe("tpl-1");
  });

  it("omits persona_id when no persona is selected", async () => {
    const onCreate = renderPanel();

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /create session/i })).not.toBeDisabled();
    });
    fireEvent.click(screen.getByRole("button", { name: /create session/i }));

    expect(onCreate).toHaveBeenCalledTimes(1);
    expect(onCreate.mock.calls[0][0].persona_id).toBeNull();
  });

  it("a Controlled PC selection takes priority over a selected persona", async () => {
    vi.mocked(entitiesApi.listSystems).mockResolvedValue([{ id: "sys-1", name: "D&D 5e" }]);
    vi.mocked(entitiesApi.listCharacters).mockResolvedValue([{ id: "char-1", name: "Existing PC" }]);

    const onCreate = renderPanel();

    await waitFor(() => {
      expect(screen.getByText("Rook")).toBeInTheDocument();
    });

    // Select a persona first.
    fireEvent.change(screen.getByLabelText(/play as a saved persona/i), {
      target: { value: "persona-1" },
    });

    // The system auto-selects (only one option), which loads the Controlled
    // PC list; select the one PC available. (The name also shows up in the
    // selection summary once picked, so match the <option> specifically.)
    await waitFor(() => {
      expect(screen.getByRole("option", { name: "Existing PC" })).toBeInTheDocument();
    });
    fireEvent.change(screen.getByLabelText(/controlled pc/i), { target: { value: "char-1" } });

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /create session/i })).not.toBeDisabled();
    });
    fireEvent.click(screen.getByRole("button", { name: /create session/i }));

    const payload = onCreate.mock.calls[0][0];
    expect(payload.character_id).toBe("char-1");
    expect(payload.persona_id).toBeNull();
  });
});

describe("SetupPanel story premise", () => {
  it("sends the typed story premise on create", async () => {
    const onCreate = renderPanel();

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /create session/i })).not.toBeDisabled();
    });

    fireEvent.change(screen.getByLabelText(/story premise/i), {
      target: { value: "  A heist against a rival Prince, no combat.  " },
    });
    fireEvent.click(screen.getByRole("button", { name: /create session/i }));

    expect(onCreate.mock.calls[0][0].story_premise).toBe("A heist against a rival Prince, no combat.");
  });

  it("sends null when left blank", async () => {
    const onCreate = renderPanel();

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /create session/i })).not.toBeDisabled();
    });
    fireEvent.click(screen.getByRole("button", { name: /create session/i }));

    expect(onCreate.mock.calls[0][0].story_premise).toBeNull();
  });
});
