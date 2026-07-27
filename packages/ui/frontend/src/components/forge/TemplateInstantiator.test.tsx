// @vitest-environment happy-dom
/**
 * Tests for TemplateInstantiator (F3-2c):
 * - client-side preview resolves naming_pattern + variable_properties
 * - Create chains templatesApi.instantiate → entitiesApi.generateEntity
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import * as api from "@/lib/api";
import type { EntityTemplate, InstantiateTemplateResponse } from "@/lib/types";
import { TemplateInstantiator } from "./TemplateInstantiator";

const UNIVERSE_ID = "11111111-1111-1111-1111-111111111111";

function makeTemplate(over: Partial<EntityTemplate> = {}): EntityTemplate {
  return {
    template_id: "22222222-2222-2222-2222-222222222222",
    universe_id: UNIVERSE_ID,
    name: "City Guard",
    description: "A rank-and-file watchman.",
    entity_type: "character",
    base_properties: { role: "guard" },
    variable_properties: [
      {
        property_path: "rank",
        generation_type: "fixed",
        options: ["recruit"],
      },
      {
        property_path: "quirk",
        generation_type: "llm",
        options: [],
        llm_hint: "a memorable nervous tic",
      },
    ],
    naming_pattern: { type: "numbered" },
    stat_generation: { method: "fixed", formulas: {}, constraints: {} },
    default_state_tags: ["on_duty"],
    default_detail_level: "stub",
    default_personality: null,
    parent_template_id: null,
    usage_count: 2,
    created_at: "2026-07-24T00:00:00Z",
    updated_at: null,
    ...over,
  };
}

const RESOLVED: InstantiateTemplateResponse = {
  template_id: "22222222-2222-2222-2222-222222222222",
  universe_id: UNIVERSE_ID,
  name: "City Guard 3",
  entity_type: "character",
  description: "A rank-and-file watchman.",
  properties: { role: "guard", rank: "recruit" },
  resolved_variables: { rank: "recruit" },
  llm_hints: { quirk: "a memorable nervous tic" },
  state_tags: ["on_duty"],
  detail_level: "stub",
  default_personality: null,
  usage_count: 3,
  scene_id: null,
  story_id: null,
};

function renderInstantiator(onCreated = vi.fn()) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <TemplateInstantiator
        template={makeTemplate()}
        open
        onClose={() => {}}
        onCreated={onCreated}
      />
    </QueryClientProvider>,
  );
  return onCreated;
}

beforeEach(() => {
  vi.restoreAllMocks();
});

describe("TemplateInstantiator", () => {
  it("previews the resolved name and variable values", () => {
    renderInstantiator();
    // Numbered naming with usage_count 2 → instance #3
    expect(screen.getByText("City Guard 3")).toBeInTheDocument();
    // Fixed variable resolved locally
    expect(screen.getByText("recruit")).toBeInTheDocument();
    // LLM variable shows its hint instead of a value
    expect(screen.getByText("a memorable nervous tic")).toBeInTheDocument();
  });

  it("chains instantiate → generateEntity on create", async () => {
    const instantiateSpy = vi
      .spyOn(api.templatesApi, "instantiate")
      .mockResolvedValue(RESOLVED);
    const generateSpy = vi.spyOn(api.entitiesApi, "generateEntity").mockResolvedValue({
      source: {},
      preview: {},
      saved: { entity_id: "entity-1" },
    });
    const onCreated = renderInstantiator();
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: /create entity/i }));

    await waitFor(() => expect(instantiateSpy).toHaveBeenCalledOnce());
    expect(instantiateSpy.mock.calls[0][0]).toBe("22222222-2222-2222-2222-222222222222");

    await waitFor(() => expect(generateSpy).toHaveBeenCalledOnce());
    const genBody = generateSpy.mock.calls[0][0];
    expect(genBody.name).toBe("City Guard 3");
    expect(genBody.universe_id).toBe(UNIVERSE_ID);
    expect(genBody.state_tags).toEqual(["on_duty"]);
    expect(genBody.save).toBe(true);
    // LLM hints are folded into the concept for elaboration
    expect(genBody.concept).toContain("a memorable nervous tic");

    await waitFor(() => expect(onCreated).toHaveBeenCalledWith("entity-1"));
  });

  it("sends the override name to the instantiate route", async () => {
    const instantiateSpy = vi
      .spyOn(api.templatesApi, "instantiate")
      .mockResolvedValue({ ...RESOLVED, name: "Sergeant Brann" });
    vi.spyOn(api.entitiesApi, "generateEntity").mockResolvedValue({
      source: {},
      preview: {},
      saved: { entity_id: "entity-2" },
    });
    renderInstantiator();
    const user = userEvent.setup();

    await user.type(screen.getByPlaceholderText("City Guard 3"), "Sergeant Brann");
    await user.click(screen.getByRole("button", { name: /create entity/i }));

    await waitFor(() => expect(instantiateSpy).toHaveBeenCalledOnce());
    expect(instantiateSpy.mock.calls[0][1]).toMatchObject({ override_name: "Sergeant Brann" });
  });
});
