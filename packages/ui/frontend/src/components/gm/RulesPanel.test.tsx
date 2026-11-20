// @vitest-environment happy-dom
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { entitiesApi } from "@/lib/api";
import type { RPGSystem } from "@/lib/types";
import { RulesPanel } from "./RulesPanel";

const SYSTEM: RPGSystem = {
  id: "sys-1",
  name: "Bound System",
  description: "A test system",
  version: null,
  core_mechanic: {
    mechanic_type: "dice",
    formula: "roll under d20",
    success_type: "roll under",
    target_number: 12,
    description: "Roll a d20 under the target.",
  },
  attributes: [{ name: "Might", abbreviation: "MIG", min_value: 1, max_value: 5, description: null }],
  skills: [],
  resources: [],
  rules: [
    {
      name: "Advantage",
      rule_type: "core",
      description: "Roll twice, keep the better.",
      formula: "2d20 keep 1",
    },
  ],
  is_builtin: false,
  source_document_id: null,
  character_count: 0,
  session_count: 0,
  needs_review: false,
  degenerate_reason: null,
} as RPGSystem;

function renderRules(systemId: string | null) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <RulesPanel systemId={systemId} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.restoreAllMocks();
});

describe("RulesPanel (P2.2)", () => {
  it("asks for a system when none is selected and fetches nothing", () => {
    const spy = vi.spyOn(entitiesApi, "getSystem");
    renderRules(null);
    expect(screen.getByText(/select an rpg system/i)).toBeInTheDocument();
    expect(spy).not.toHaveBeenCalled();
  });

  it("renders the bound system's mechanic, attributes and rules", async () => {
    const spy = vi.spyOn(entitiesApi, "getSystem").mockResolvedValue(SYSTEM);
    renderRules("sys-1");

    await waitFor(() => expect(spy).toHaveBeenCalledWith("sys-1"));
    expect(await screen.findByText("roll under d20")).toBeInTheDocument();
    expect(screen.getByText("MIG")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /advantage/i })).toBeInTheDocument();
    expect(screen.getByText("A test system")).toBeInTheDocument();
  });
});
