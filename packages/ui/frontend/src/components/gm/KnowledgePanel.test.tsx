// @vitest-environment happy-dom
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { entitiesApi } from "@/lib/api";
import { gmTableApi } from "@/lib/gm-table-api";
import { KnowledgePanel } from "./KnowledgePanel";

function renderPanel(universeId: string | null) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <KnowledgePanel universeId={universeId} />
    </QueryClientProvider>,
  );
}

const AUDIT = {
  entity_id: "char-1",
  universe_id: "u-1",
  fact_count: 1,
  memory_count: 1,
  proposal_count: 0,
  suspicious_count: 1,
  items: [
    {
      id: "fact-1",
      kind: "fact" as const,
      statement: "The gate opened.",
      source: "witnessed" as const,
      scene_id: null,
      importance: 0,
      certainty: 1,
      confidence: 1,
      canon_level: "canon",
      suspicious: false,
      suspicion_reason: "",
    },
    {
      id: "mem-1",
      kind: "memory" as const,
      statement: "The council met without her.",
      source: "memory" as const,
      scene_id: "scene-1",
      importance: 0.9,
      certainty: 0.2,
      confidence: 1,
      canon_level: "",
      suspicious: true,
      suspicion_reason: "Important to them but they are not sure of it.",
    },
  ],
};

beforeEach(() => {
  vi.restoreAllMocks();
  globalThis.fetch = vi.fn(() =>
    Promise.resolve(new Response("[]", { status: 200, headers: { "Content-Type": "application/json" } })),
  ) as unknown as typeof fetch;
  vi.spyOn(entitiesApi, "listNPCs").mockResolvedValue({
    items: [{ id: "char-1", name: "Mira" }],
    total: 1,
  } as never);
  vi.spyOn(gmTableApi, "auditKnowledge").mockResolvedValue(AUDIT);
  vi.spyOn(gmTableApi, "challengeKnowledge").mockResolvedValue({
    proposal_id: "p-1",
    entity_id: "char-1",
  });
});

describe("KnowledgePanel (CF-15)", () => {
  it("prompts for a universe when none is selected", () => {
    renderPanel(null);
    expect(screen.getByText(/select a universe to inspect knowledge/i)).toBeInTheDocument();
  });

  it("lists the universe's characters", async () => {
    renderPanel("u-1");
    expect(await screen.findByText("Mira")).toBeInTheDocument();
  });

  it("shows what the character knows, with its provenance", async () => {
    renderPanel("u-1");
    await userEvent.click(await screen.findByText("Mira"));

    expect(await screen.findByText("The gate opened.")).toBeInTheDocument();
    expect(screen.getByText("witnessed")).toBeInTheDocument();
    expect(screen.getByText("their memory")).toBeInTheDocument();
  });

  it("marks a doubtful attribution and says why", async () => {
    renderPanel("u-1");
    await userEvent.click(await screen.findByText("Mira"));

    await waitFor(() => expect(screen.getByText("The council met without her.")).toBeInTheDocument());
    expect(screen.getByText(/Important to them/)).toBeInTheDocument();
    expect(screen.getByLabelText("Doubtful attribution")).toBeInTheDocument();
  });

  it("challenging an attribution stages a correction", async () => {
    renderPanel("u-1");
    await userEvent.click(await screen.findByText("Mira"));
    await waitFor(() => expect(screen.getByText("The council met without her.")).toBeInTheDocument());

    await userEvent.click(screen.getAllByLabelText("Challenge this attribution")[0]);

    await waitFor(() => expect(gmTableApi.challengeKnowledge).toHaveBeenCalled());
    const [universeId, entityId, body] = vi.mocked(gmTableApi.challengeKnowledge).mock.calls[0];
    expect(universeId).toBe("u-1");
    expect(entityId).toBe("char-1");
    expect(body.action).toBe("retract");
    expect(body.item_id).toBe("fact-1");
  });

  it("says when the system attributes nothing", async () => {
    vi.spyOn(gmTableApi, "auditKnowledge").mockResolvedValue({
      ...AUDIT,
      items: [],
      fact_count: 0,
      memory_count: 0,
      proposal_count: 0,
      suspicious_count: 0,
    });
    renderPanel("u-1");
    await userEvent.click(await screen.findByText("Mira"));

    expect(await screen.findByText(/attributes nothing to this character/i)).toBeInTheDocument();
  });
});
