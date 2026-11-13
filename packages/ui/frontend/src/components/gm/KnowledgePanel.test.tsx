// @vitest-environment happy-dom
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { entitiesApi, storiesApi } from "@/lib/api";
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
  vi.spyOn(storiesApi, "listStories").mockResolvedValue({ stories: [{ id: "story-1", title: "Harbour" }], total: 1 } as never);
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

  it("loads later pages of attributed knowledge", async () => {
    vi.mocked(gmTableApi.auditKnowledge).mockImplementation(async (_universe, _entity, offset) =>
      offset ? { ...AUDIT, items: [{ ...AUDIT.items[0], statement: "Later fact" }], next_offset: null }
        : { ...AUDIT, next_offset: 200 },
    );
    renderPanel("u-1");
    await userEvent.click(await screen.findByText("Mira"));
    await userEvent.click(await screen.findByRole("button", { name: "Next page" }));
    expect(await screen.findByText("Later fact")).toBeInTheDocument();
    expect(gmTableApi.auditKnowledge).toHaveBeenCalledWith("u-1", "char-1", 200);
    expect(screen.getByRole("button", { name: "Previous page" })).toBeInTheDocument();
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

    await userEvent.selectOptions(await screen.findByLabelText("Story for challenges"), "story-1");

    await userEvent.click(screen.getAllByLabelText("Challenge this attribution")[0]);
    await userEvent.type(screen.getByLabelText("Reason for challenge"), "Mira was not present.");
    await userEvent.click(screen.getByRole("button", { name: "Submit challenge" }));

    await waitFor(() => expect(gmTableApi.challengeKnowledge).toHaveBeenCalled());
    const [universeId, entityId, body] = vi.mocked(gmTableApi.challengeKnowledge).mock.calls[0];
    expect(universeId).toBe("u-1");
    expect(entityId).toBe("char-1");
    expect(body.action).toBe("retract");
    expect(body.item_id).toBe("fact-1");
    expect(body.story_id).toBe("story-1");
    expect(body.reason).toBe("Mira was not present.");
  });

  it("lets the GM provide a corrected statement and reason", async () => {
    renderPanel("u-1");
    await userEvent.click(await screen.findByText("Mira"));
    await userEvent.selectOptions(await screen.findByLabelText("Story for challenges"), "story-1");
    await userEvent.click((await screen.findAllByLabelText("Challenge this attribution"))[0]);
    await userEvent.selectOptions(screen.getByLabelText("Challenge action"), "correct");
    const field = screen.getByLabelText("Corrected statement");
    await userEvent.clear(field);
    await userEvent.type(field, "The gate remained closed.");
    await userEvent.type(screen.getByLabelText("Reason for challenge"), "The earlier entry was wrong.");
    await userEvent.click(screen.getByRole("button", { name: "Submit challenge" }));
    await waitFor(() => expect(gmTableApi.challengeKnowledge).toHaveBeenCalled());
    expect(vi.mocked(gmTableApi.challengeKnowledge).mock.calls[0][2]).toMatchObject({
      action: "correct", statement: "The gate remained closed.", reason: "The earlier entry was wrong.",
    });
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
