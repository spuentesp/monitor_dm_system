// @vitest-environment happy-dom
/**
 * Forge overview dashboard tests (F1-2):
 * - KPI cards + links
 * - selected-world highlight (WorldContext / localStorage)
 * - jobs attention table (status mapping, error text, actions, non-UUID ids)
 * - pipeline health chip states (incl. watchdog disabled ≠ healthy)
 * - review card = packs with review_pending (not proposal totals)
 * - partial query failure (one card errors, others still render)
 * - ?pack=/?universe= deep-link forwarding
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { WorldContextProvider } from "@/lib/world-context";
import { NotificationProvider } from "@/components/NotificationProvider";
import { ingestApi, jobsHealthApi, universesApi } from "@/lib/api";
import type { IngestJob, JobsHealthResponse, KnowledgePack, Universe } from "@/lib/types";
import { derivePipelineHealth } from "@/components/forge/PipelineHealthChip";
import ForgeOverviewPage from "./page";

// ─── next/navigation mock ─────────────────────────────────────

const nav = vi.hoisted(() => ({
  params: "",
  replace: vi.fn(),
  push: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(nav.params),
  useRouter: () => ({ replace: nav.replace, push: nav.push }),
}));

// ─── Fixtures ─────────────────────────────────────────────────

const UUID_1 = "11111111-1111-1111-1111-111111111111";
const UUID_2 = "22222222-2222-2222-2222-222222222222";

function universe(id: string, name: string, created = "2026-07-01T00:00:00Z"): Universe {
  return {
    id,
    name,
    multiverse_id: "mv-1",
    genre: "Fantasy",
    description: null,
    tags: [],
    is_active: true,
    entity_count: 12,
    session_count: 0,
    created_at: created,
  };
}

function pack(id: string, name: string, status: KnowledgePack["status"]): KnowledgePack {
  return {
    id,
    name,
    description: null,
    pack_type: "setting",
    status,
    system_name: null,
    game_system_id: null,
    game_system: null,
    game_system_data: null,
    source_profile_data: null,
    chunk_summaries: [],
    section_summaries: [],
    source_mindscape: null,
    tags: [],
    axiom_count: 1,
    entity_count: 2,
    lore_fact_count: 3,
    axioms: [],
    entity_archetypes: [],
    lore_facts: [],
    entity_relationships: [],
    created_at: "2026-07-02T00:00:00Z",
    updated_at: null,
    applied_to: [],
    parent_pack_ids: [],
    source_document_ids: [],
  };
}

function job(overrides: Partial<IngestJob>): IngestJob {
  return {
    id: UUID_1,
    source_id: "src-1",
    source_title: "Corebook PDF",
    job_type: "ingest",
    status: "running",
    progress: 40,
    current_stage: "extracting",
    stages_completed: [],
    processing_checklist: [],
    activity_log: [],
    warnings: [],
    errors: [],
    snippet_count: 0,
    entities_extracted: 0,
    axioms_extracted: 0,
    proposals_generated: 0,
    started_at: new Date().toISOString(),
    completed_at: null,
    duration_seconds: null,
    error: null,
    pack_id: null,
    ...overrides,
  };
}

function health(overrides: Partial<JobsHealthResponse> = {}): JobsHealthResponse {
  return {
    watchdog: { enabled: true, is_running: true, last_scanned: 4, last_failed: 0, last_skipped: 0 },
    counts: {
      pending: 0,
      running: 1,
      failed: 0,
      completed: 3,
      partial: 0,
      flagged_duplicate: 0,
      blocked_provider: 0,
    },
    stale: [],
    generated_at: new Date().toISOString(),
    ...overrides,
  };
}

function seedSelectedWorld(id: string, label: string) {
  window.localStorage.setItem(
    "monitor.world-context.v1",
    JSON.stringify({ multiverseId: null, universeId: id, universeLabel: label }),
  );
}

// ─── Render helper ────────────────────────────────────────────

function renderDashboard() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <WorldContextProvider>
        <NotificationProvider>
          <ForgeOverviewPage />
        </NotificationProvider>
      </WorldContextProvider>
    </QueryClientProvider>,
  );
}

function mockAll({
  universes = [universe(UUID_1, "Ashen Vale"), universe(UUID_2, "Neon Drift", "2026-07-03T00:00:00Z")],
  packs = [pack("p1", "Ashen Vale Pack", "review_pending"), pack("p2", "Rules Pack", "ready")],
  jobs = [job({})],
  healthData = health(),
}: {
  universes?: Universe[];
  packs?: KnowledgePack[];
  jobs?: IngestJob[];
  healthData?: JobsHealthResponse;
} = {}) {
  vi.spyOn(universesApi, "listUniverses").mockResolvedValue(universes);
  vi.spyOn(ingestApi, "listPacks").mockResolvedValue(packs);
  vi.spyOn(ingestApi, "listJobs").mockResolvedValue(jobs);
  vi.spyOn(jobsHealthApi, "health").mockResolvedValue(healthData);
}

beforeEach(() => {
  vi.restoreAllMocks();
  nav.params = "";
  nav.replace.mockReset();
  nav.push.mockReset();
  window.localStorage.clear();
});

// ─── KPI cards & links ────────────────────────────────────────

describe("Forge dashboard — KPI cards", () => {
  it("renders world/pack/job counts and links", async () => {
    mockAll();
    renderDashboard();

    const worldsTile = screen.getByTestId("kpi-worlds");
    await waitFor(() => expect(within(worldsTile).getByText("2")).toBeInTheDocument());
    expect(worldsTile).toHaveAttribute("href", "/forge/worlds");

    const packsTile = screen.getByTestId("kpi-packs");
    expect(within(packsTile).getByText("2")).toBeInTheDocument();
    expect(packsTile).toHaveAttribute("href", "/forge/packs");

    const activeTile = screen.getByTestId("kpi-active-jobs");
    expect(within(activeTile).getByText("1")).toBeInTheDocument();
    expect(activeTile).toHaveAttribute("href", "/forge/ingest");
  });

  it("quick actions link to worlds/ingest/architect and the selected world", async () => {
    mockAll();
    seedSelectedWorld(UUID_1, "Ashen Vale");
    renderDashboard();

    expect(screen.getByTestId("action-new-world")).toHaveAttribute("href", "/forge/worlds/new");
    expect(screen.getByRole("link", { name: /upload source/i })).toHaveAttribute("href", "/forge/ingest");
    expect(screen.getByRole("link", { name: /open architect/i })).toHaveAttribute("href", "/forge/architect");

    await waitFor(() =>
      expect(screen.getByTestId("action-open-world")).toHaveAttribute(
        "href",
        `/forge/worlds?universe=${UUID_1}`,
      ),
    );
  });
});

// ─── Selected world ───────────────────────────────────────────

describe("Forge dashboard — selected world", () => {
  it("shows the selected-world chip and highlights the matching world card", async () => {
    mockAll();
    seedSelectedWorld(UUID_1, "Ashen Vale");
    renderDashboard();

    const chip = await screen.findByTestId("selected-world-chip");
    expect(chip).toHaveTextContent("Selected world:");
    expect(chip).toHaveTextContent("Ashen Vale");

    const card = await screen.findByTestId(`world-card-${UUID_1}`);
    expect(card).toHaveAttribute("aria-current", "true");
    expect(within(card).getByText("Selected")).toBeInTheDocument();

    const other = screen.getByTestId(`world-card-${UUID_2}`);
    expect(other).not.toHaveAttribute("aria-current");
  });

  it("renders without a chip when nothing is selected", async () => {
    mockAll();
    renderDashboard();
    await screen.findByTestId(`world-card-${UUID_1}`);
    expect(screen.queryByTestId("selected-world-chip")).not.toBeInTheDocument();
  });
});

// ─── Jobs attention table ─────────────────────────────────────

describe("Forge dashboard — jobs attention table", () => {
  it("shows failed jobs with their error text and a working Re-run action", async () => {
    const failedJob = job({
      id: UUID_2,
      status: "failed",
      progress: 55,
      current_stage: "canonizing",
      error: "LLM provider timeout",
      source_id: "src-broken",
      started_at: new Date().toISOString(),
    });
    mockAll({ jobs: [failedJob] });
    const rescan = vi.spyOn(ingestApi, "rescanSource").mockResolvedValue({
      status: "queued",
      source_id: "src-broken",
      source_title: "Corebook PDF",
      message: "ok",
    });

    const user = userEvent.setup();
    renderDashboard();

    const row = await screen.findByTestId(`attention-job-${UUID_2}`);
    expect(within(row).getByText("failed")).toBeInTheDocument();
    expect(within(row).getByText(/LLM provider timeout/)).toBeInTheDocument();
    expect(within(row).getByText(/failed at|canonizing/)).toBeInTheDocument();

    await user.click(within(row).getByRole("button", { name: /re-run/i }));
    await waitFor(() => expect(rescan).toHaveBeenCalledWith("src-broken"));
  });

  it("shows live jobs with progress and Cancel — but no Cancel for non-UUID ids", async () => {
    const liveReal = job({ id: UUID_1, status: "running", progress: 30 });
    const livePlaceholder = job({
      id: "local-placeholder",
      source_title: "Optimistic row",
      status: "pending",
      progress: 0,
    });
    mockAll({ jobs: [liveReal, livePlaceholder] });
    const cancel = vi.spyOn(ingestApi, "cancelJob").mockResolvedValue({
      job_id: UUID_1,
      status: "cancelled",
      message: "ok",
    });

    const user = userEvent.setup();
    renderDashboard();

    const realRow = await screen.findByTestId(`attention-job-${UUID_1}`);
    expect(within(realRow).getByRole("progressbar")).toHaveAttribute("aria-valuenow", "30");
    await user.click(within(realRow).getByRole("button", { name: /cancel/i }));
    await waitFor(() => expect(cancel).toHaveBeenCalledWith(UUID_1));

    const placeholderRow = screen.getByTestId("attention-job-local-placeholder");
    expect(within(placeholderRow).queryByRole("button", { name: /cancel/i })).not.toBeInTheDocument();
  });

  it("keeps completed jobs out of the attention table", async () => {
    const done = job({
      id: UUID_2,
      status: "completed",
      progress: 100,
      proposals_generated: 7,
      pack_id: "pack-42",
    });
    mockAll({ jobs: [done] });
    renderDashboard();

    // completed + not failed → not attention-worthy; the empty state shows
    await waitFor(() =>
      expect(screen.getByText(/nothing running or broken/i)).toBeInTheDocument(),
    );
    expect(screen.queryByTestId(`attention-job-${UUID_2}`)).not.toBeInTheDocument();
  });

  it("offers an Unlock queue action when jobs need attention", async () => {
    mockAll({ jobs: [job({ id: UUID_1, status: "failed", error: "boom" })] });
    const unlock = vi.spyOn(ingestApi, "unlockQueue").mockResolvedValue({
      unlocked: true,
      was_locked_by: null,
      cleared_pending: 1,
      cleared_active: 0,
      recovered_jobs: 1,
    });

    const user = userEvent.setup();
    renderDashboard();

    const btn = await screen.findByRole("button", { name: /unlock queue/i });
    await user.click(btn);
    await waitFor(() => expect(unlock).toHaveBeenCalled());
  });

  it("marks jobs as stale using the health stale list", async () => {
    mockAll({
      jobs: [job({ id: UUID_1, status: "running", progress: 10 })],
      healthData: health({
        stale: [
          {
            job_id: UUID_1,
            source_title: "Corebook PDF",
            last_progress_at: new Date(Date.now() - 60 * 60_000).toISOString(),
            stale_for_min: 60,
          },
        ],
      }),
    });
    renderDashboard();

    const row = await screen.findByTestId(`attention-job-${UUID_1}`);
    expect(within(row).getByText("stale")).toBeInTheDocument();
    expect(await screen.findByText(/1 stale job \(no recent progress\)/)).toBeInTheDocument();
  });
});

// ─── Review card ──────────────────────────────────────────────

describe("Forge dashboard — review card", () => {
  it("counts only packs with status review_pending and links to /forge/review", async () => {
    mockAll();
    renderDashboard();

    const section = await screen.findByRole("region", { name: /packs awaiting review/i });
    const link = await within(section).findByRole("link", { name: /ashen vale pack/i });
    expect(link).toHaveAttribute("href", "/forge/review?pack=p1");
    // The "ready" pack must not appear in the review card.
    expect(within(section).queryByText("Rules Pack")).not.toBeInTheDocument();

    expect(await screen.findByText("1 pack awaiting review")).toBeInTheDocument();
  });

  it("shows the empty state when no pack is awaiting review", async () => {
    mockAll({ packs: [pack("p2", "Rules Pack", "ready")] });
    renderDashboard();
    expect(await screen.findByText(/nothing waiting on a human decision/i)).toBeInTheDocument();
  });
});

// ─── Health chip states ───────────────────────────────────────

describe("derivePipelineHealth — state mapping", () => {
  it("maps unreachable when the query errors", () => {
    expect(derivePipelineHealth(undefined, true, false).state).toBe("unreachable");
  });

  it("distinguishes watchdog disabled from healthy", () => {
    const disabled = derivePipelineHealth(
      health({ watchdog: { enabled: false, is_running: false, last_scanned: 0, last_failed: 0, last_skipped: 0 } }),
      false,
      false,
    );
    expect(disabled.state).toBe("watchdog_disabled");

    const ok = derivePipelineHealth(
      health({ counts: { pending: 0, running: 0, failed: 0, completed: 0, partial: 0, flagged_duplicate: 0, blocked_provider: 0 } }),
      false,
      false,
    );
    expect(ok.state).toBe("healthy");
  });

  it("prioritizes stale over failed/blocked, and failed over active", () => {
    const stale = derivePipelineHealth(
      health({
        counts: { pending: 0, running: 1, failed: 2, completed: 0, partial: 0, flagged_duplicate: 0, blocked_provider: 1 },
        stale: [{ job_id: "j1", source_title: "t", last_progress_at: null, stale_for_min: 50 }],
      }),
      false,
      false,
    );
    expect(stale.state).toBe("stale");
    expect(stale.label).toBe("1 stale job");

    const attention = derivePipelineHealth(
      health({ counts: { pending: 1, running: 1, failed: 1, completed: 0, partial: 0, flagged_duplicate: 0, blocked_provider: 0 } }),
      false,
      false,
    );
    expect(attention.state).toBe("attention");
    expect(attention.label).toContain("1 failed");

    const active = derivePipelineHealth(health(), false, false);
    expect(active.state).toBe("active");
  });
});

describe("Forge dashboard — health chip rendering", () => {
  it("renders healthy state with generated_at", async () => {
    mockAll({
      jobs: [],
      healthData: health({
        counts: { pending: 0, running: 0, failed: 0, completed: 5, partial: 0, flagged_duplicate: 0, blocked_provider: 0 },
      }),
    });
    renderDashboard();
    const chip = await screen.findByTestId("pipeline-health-chip");
    await waitFor(() => expect(chip).toHaveAttribute("data-state", "healthy"));
    expect(chip).toHaveTextContent("Pipeline healthy");
  });

  it("renders watchdog disabled distinctly from healthy", async () => {
    mockAll({
      jobs: [],
      healthData: health({
        watchdog: { enabled: false, is_running: false, last_scanned: 0, last_failed: 0, last_skipped: 0 },
        counts: { pending: 0, running: 0, failed: 0, completed: 0, partial: 0, flagged_duplicate: 0, blocked_provider: 0 },
      }),
    });
    renderDashboard();
    const chip = await screen.findByTestId("pipeline-health-chip");
    await waitFor(() => expect(chip).toHaveAttribute("data-state", "watchdog_disabled"));
    expect(chip).toHaveTextContent("Watchdog disabled");
  });

  it("renders unreachable when the health endpoint fails", async () => {
    mockAll({ jobs: [] });
    vi.spyOn(jobsHealthApi, "health").mockRejectedValue(new Error("ECONNREFUSED"));
    renderDashboard();
    const chip = await screen.findByTestId("pipeline-health-chip");
    await waitFor(() => expect(chip).toHaveAttribute("data-state", "unreachable"));
    expect(chip).toHaveTextContent("Health unreachable");
  });
});

// ─── Partial failure ──────────────────────────────────────────

describe("Forge dashboard — partial query failure", () => {
  it("keeps world/pack cards when the jobs endpoint fails", async () => {
    mockAll();
    vi.spyOn(ingestApi, "listJobs").mockRejectedValue(new Error("jobs down"));
    renderDashboard();

    // Jobs section shows its own error…
    expect(await screen.findByText(/couldn’t load ingestion jobs/i)).toBeInTheDocument();
    // …while other cards still render their data.
    const worldsTile = screen.getByTestId("kpi-worlds");
    await waitFor(() => expect(within(worldsTile).getByText("2")).toBeInTheDocument());
    expect(await screen.findByTestId(`world-card-${UUID_1}`)).toBeInTheDocument();
    expect(screen.getByTestId("pipeline-health-chip")).toBeInTheDocument();
  });

  it("keeps the jobs table when the packs endpoint fails", async () => {
    mockAll({ jobs: [job({ id: UUID_1, status: "failed", error: "boom" })] });
    vi.spyOn(ingestApi, "listPacks").mockRejectedValue(new Error("packs down"));
    renderDashboard();

    expect(await screen.findByTestId(`attention-job-${UUID_1}`)).toBeInTheDocument();
    // KPI tile + recent-packs section each render their own error note.
    const errors = await screen.findAllByText(/couldn’t load packs/i);
    expect(errors.length).toBeGreaterThan(0);
  });
});

// ─── Deep links ───────────────────────────────────────────────

describe("Forge dashboard — deep-link forwarding", () => {
  it("forwards ?pack= to /forge/packs?pack=", async () => {
    nav.params = "pack=pack-99";
    mockAll();
    renderDashboard();
    await waitFor(() =>
      expect(nav.replace).toHaveBeenCalledWith("/forge/packs?pack=pack-99"),
    );
  });

  it("forwards ?universe= to /forge/worlds?universe=", async () => {
    nav.params = `universe=${UUID_1}`;
    mockAll();
    renderDashboard();
    await waitFor(() =>
      expect(nav.replace).toHaveBeenCalledWith(`/forge/worlds?universe=${UUID_1}`),
    );
  });
});
