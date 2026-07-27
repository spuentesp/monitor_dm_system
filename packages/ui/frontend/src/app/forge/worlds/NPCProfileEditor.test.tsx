// @vitest-environment happy-dom
/**
 * NPC profile editor tests (F2-2 phase 5):
 * - the /forge/worlds detail panel shows the psyche summary and opens the
 *   editor from the pencil button
 * - the editor hydrates from GET /npcs/{id}/profile and PUTs the full
 *   writable subset, parsing traits / line lists / JSON lists
 * - a 404 profile means "not written yet": the form starts empty and the
 *   same PUT upserts it
 * - malformed traits or JSON lists block the save with a form error
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { entitiesApi } from "@/lib/api";
import type { NPCDetail, NPCProfile } from "@/lib/types";
import { NPCDetailPanel } from "./NPCDetailPanel";
import { NPCProfileEditor } from "./NPCProfileEditor";

// ─── Fixtures ─────────────────────────────────────────────────

const NPC: NPCDetail = {
  id: "npc-1",
  name: "Mira",
  entity_type: "character",
  universe_id: "u-1",
  universe_name: "Ashen Vale",
  description: "A debt-ridden ferryman.",
  state_tags: [],
  properties: {},
  memory_count: 0,
  canon_level: "canon",
  is_archetype: false,
  memories: [],
  stats: {},
  relationships: [],
  facts: [],
};

function profile(overrides: Partial<NPCProfile> = {}): NPCProfile {
  return {
    profile_id: "p-1",
    entity_id: "npc-1",
    universe_id: "u-1",
    traits: { openness: 0.8 },
    values: ["honor"],
    fears: ["drowning"],
    desires: ["peace"],
    speech_style: "terse",
    catchphrases: [],
    mannerisms: ["tugs ear when lying"],
    emotional_tendencies: [{ emotion: "anger", baseline: 0.3, volatility: 0.7 }],
    preferences: [],
    triggers: [
      { condition: "asked about the guild", reaction: "goes quiet", intensity: 0.7, is_hidden: true },
    ],
    secrets: ["is the ferryman who let the bridge fall"],
    gm_notes: "Keep alive until act 2.",
    current_emotional_state: "wary",
    relationship_states: {},
    created_at: "2026-07-01T00:00:00Z",
    updated_at: null,
    ...overrides,
  };
}

/** ApiError-shaped 404 from the entities API. */
function notFound(): Error & { status: number } {
  const err = new Error("NPC profile not found") as Error & { status: number };
  err.status = 404;
  return err;
}

function renderWithClient(node: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{node}</QueryClientProvider>);
}

beforeEach(() => {
  vi.restoreAllMocks();
});

// ─── Detail panel integration ─────────────────────────────────

describe("NPCDetailPanel — psyche section", () => {
  it("shows a profile summary and opens the editor", async () => {
    const user = userEvent.setup();
    vi.spyOn(entitiesApi, "getNPC").mockResolvedValue(NPC);
    vi.spyOn(entitiesApi, "getNPCProfile").mockResolvedValue(profile());
    renderWithClient(<NPCDetailPanel npcId="npc-1" onClose={() => {}} />);

    expect(await screen.findByText(/Voice:/)).toBeInTheDocument();
    expect(screen.getByText(/1 traits · 1 triggers · 1 secrets/)).toBeInTheDocument();

    await user.click(screen.getByLabelText("Edit NPC profile"));
    expect(await screen.findByText(/NPC profile — Mira/)).toBeInTheDocument();
    expect(screen.getByLabelText("GM notes")).toHaveValue("Keep alive until act 2.");
  });

  it("shows the empty state when no profile exists yet", async () => {
    vi.spyOn(entitiesApi, "getNPC").mockResolvedValue(NPC);
    vi.spyOn(entitiesApi, "getNPCProfile").mockRejectedValue(notFound());
    renderWithClient(<NPCDetailPanel npcId="npc-1" onClose={() => {}} />);

    expect(
      await screen.findByText(/No psyche profile yet/),
    ).toBeInTheDocument();
  });
});

// ─── Editor modal ─────────────────────────────────────────────

describe("NPCProfileEditor", () => {
  it("saves the full writable subset, parsed into API shape", async () => {
    const user = userEvent.setup();
    vi.spyOn(entitiesApi, "getNPCProfile").mockResolvedValue(profile());
    const saveSpy = vi
      .spyOn(entitiesApi, "updateNPCProfile")
      .mockResolvedValue(profile());
    const onClose = vi.fn();
    renderWithClient(
      <NPCProfileEditor npcId="npc-1" npcName="Mira" onClose={onClose} />,
    );

    // Hydrated from the fetched profile.
    expect(await screen.findByLabelText("Speech style")).toHaveValue("terse");

    const notes = screen.getByLabelText("GM notes");
    await user.clear(notes);
    await user.type(notes, "Kill her in act 1 instead.");
    fireEvent.change(screen.getByLabelText("Traits"), {
      target: { value: "openness = 0.8\nconscientiousness = 0.3" },
    });
    fireEvent.change(screen.getByLabelText("Values"), {
      target: { value: "honor\nfamily" },
    });

    await user.click(screen.getByRole("button", { name: /save profile/i }));

    await waitFor(() =>
      expect(saveSpy).toHaveBeenCalledWith(
        "npc-1",
        expect.objectContaining({
          gm_notes: "Kill her in act 1 instead.",
          speech_style: "terse",
          current_emotional_state: "wary",
          traits: { openness: 0.8, conscientiousness: 0.3 },
          values: ["honor", "family"],
          fears: ["drowning"],
          secrets: ["is the ferryman who let the bridge fall"],
          emotional_tendencies: [{ emotion: "anger", baseline: 0.3, volatility: 0.7 }],
          triggers: [
            {
              condition: "asked about the guild",
              reaction: "goes quiet",
              intensity: 0.7,
              is_hidden: true,
            },
          ],
        }),
      ),
    );
    await waitFor(() => expect(onClose).toHaveBeenCalled());
  });

  it("starts empty on a 404 and creates the profile via PUT", async () => {
    const user = userEvent.setup();
    vi.spyOn(entitiesApi, "getNPCProfile").mockRejectedValue(notFound());
    const saveSpy = vi
      .spyOn(entitiesApi, "updateNPCProfile")
      .mockResolvedValue(profile());
    renderWithClient(<NPCProfileEditor npcId="npc-1" onClose={() => {}} />);

    expect(
      await screen.findByText(/No profile exists for this NPC yet/),
    ).toBeInTheDocument();

    await user.type(screen.getByLabelText("Speech style"), "formal and verbose");
    await user.click(screen.getByRole("button", { name: /create profile/i }));

    await waitFor(() =>
      expect(saveSpy).toHaveBeenCalledWith(
        "npc-1",
        expect.objectContaining({ speech_style: "formal and verbose", traits: {} }),
      ),
    );
  });

  it("blocks the save on a malformed trait line", async () => {
    const user = userEvent.setup();
    vi.spyOn(entitiesApi, "getNPCProfile").mockResolvedValue(profile());
    const saveSpy = vi
      .spyOn(entitiesApi, "updateNPCProfile")
      .mockResolvedValue(profile());
    renderWithClient(<NPCProfileEditor npcId="npc-1" onClose={() => {}} />);
    await screen.findByLabelText("Traits");

    fireEvent.change(screen.getByLabelText("Traits"), {
      target: { value: "openness = 7" },
    });
    await user.click(screen.getByRole("button", { name: /save profile/i }));

    expect(await screen.findByText(/score must be 0–1/)).toBeInTheDocument();
    expect(saveSpy).not.toHaveBeenCalled();
  });

  it("blocks the save on invalid triggers JSON", async () => {
    const user = userEvent.setup();
    vi.spyOn(entitiesApi, "getNPCProfile").mockResolvedValue(profile());
    const saveSpy = vi
      .spyOn(entitiesApi, "updateNPCProfile")
      .mockResolvedValue(profile());
    renderWithClient(<NPCProfileEditor npcId="npc-1" onClose={() => {}} />);
    await screen.findByLabelText("Behavioral triggers");

    fireEvent.change(screen.getByLabelText("Behavioral triggers"), {
      target: { value: "{broken" },
    });
    await user.click(screen.getByRole("button", { name: /save profile/i }));

    expect(
      await screen.findByText(/Behavioral triggers is not valid JSON/),
    ).toBeInTheDocument();
    expect(saveSpy).not.toHaveBeenCalled();
  });
});
