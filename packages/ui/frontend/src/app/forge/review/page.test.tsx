// @vitest-environment happy-dom
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import * as api from "@/lib/api";
import type { CanonQueue, IngestJob, IngestJobReview, ProposalItem, SceneReview } from "@/lib/types";
import ReviewPage from "./page";

// Mutable search params so each test can set its own deep link; the replace
// mock applies the navigation so the URL ↔ state sync stays consistent.
let searchParams = new URLSearchParams();
const pushMock = vi.fn();
const replaceMock = vi.fn((url: string) => {
  const q = url.includes("?") ? url.slice(url.indexOf("?") + 1) : url;
  searchParams = new URLSearchParams(q);
});
vi.mock("next/navigation", () => ({
  useSearchParams: () => searchParams,
  useRouter: () => ({ push: pushMock, replace: replaceMock }),
}));

const JOB_ID = "33333333-3333-3333-3333-333333333333";
const STORY_ID = "11111111-1111-1111-1111-111111111111";

function proposal(id: string, status: "pending" | "accepted" | "rejected" = "pending"): ProposalItem {
  return {
    proposal_id: id,
    change_type: "fact",
    content: { statement: `Statement ${id}` },
    confidence: 0.95,
    authority: "source",
    proposer: "IngestionPipeline",
    status,
    evidence: [],
    created_at: null,
    proposal_type: "create_lore_fact",
    source: `ingestion_job:${JOB_ID}`,
  };
}

function job(id: string, status = "completed"): IngestJob {
  return {
    id,
    source_id: "src-1",
    source_title: "Core Rulebook",
    job_type: "ingest",
    status,
    progress: 100,
    current_stage: null,
    stages_completed: [],
    processing_checklist: [],
    activity_log: [],
    warnings: [],
    errors: [],
    snippet_count: 10,
    entities_extracted: 3,
    axioms_extracted: 2,
    proposals_generated: 2,
    started_at: null,
    completed_at: null,
    duration_seconds: null,
    error: null,
    pack_id: null,
  };
}

function jobReview(pending: ProposalItem[], accepted: ProposalItem[] = []): IngestJobReview {
  return {
    ingestion_job_id: JOB_ID,
    pending,
    accepted,
    rejected: [],
    by_change_type: { fact: pending.length + accepted.length },
  };
}

function storyQueue(scenes: SceneReview[]): CanonQueue {
  return {
    story_id: STORY_ID,
    scenes,
    total_pending: scenes.reduce((n, s) => n + s.pending.length, 0),
  };
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ReviewPage />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.restoreAllMocks();
  pushMock.mockClear();
  replaceMock.mockClear();
  searchParams = new URLSearchParams();
  globalThis.fetch = vi.fn(() =>
    Promise.resolve(new Response("[]", { status: 200, headers: { "Content-Type": "application/json" } })),
  ) as unknown as typeof fetch;
});

describe("/forge/review — scope switcher (F2-3a)", () => {
  it("defaults to the pack scope and switches between the three scopes", async () => {
    vi.spyOn(api.ingestApi, "listJobs").mockResolvedValue([]);
    vi.spyOn(api.storiesApi, "listStories").mockResolvedValue({ stories: [], total: 0 });
    const user = userEvent.setup();

    renderPage();

    // Default: pack scope prompt
    expect(await screen.findByText(/select a pack to review proposals/i)).toBeInTheDocument();

    // Switch to ingestion jobs
    await user.click(screen.getByRole("button", { name: /ingestion jobs/i }));
    expect(await screen.findByText(/select an ingestion job/i)).toBeInTheDocument();

    // Switch to story / scene
    await user.click(screen.getByRole("button", { name: /story \/ scene/i }));
    expect(await screen.findByText(/select a story to review canon proposals/i)).toBeInTheDocument();
  });

  it("persists scope changes to the URL (?scope=…)", async () => {
    vi.spyOn(api.ingestApi, "listJobs").mockResolvedValue([]);
    const user = userEvent.setup();

    renderPage();
    await user.click(screen.getByRole("button", { name: /ingestion jobs/i }));

    expect(replaceMock).toHaveBeenCalled();
    const lastUrl = replaceMock.mock.calls.at(-1)![0] as string;
    expect(new URLSearchParams(lastUrl.slice(1)).get("scope")).toBe("ingest");
  });
});

describe("/forge/review — URL filter state (F2-3a)", () => {
  it("writes filter changes to the URL query parameters", async () => {
    searchParams = new URLSearchParams(`job=${JOB_ID}`);
    vi.spyOn(api.ingestApi, "listJobs").mockResolvedValue([job(JOB_ID)]);
    vi.spyOn(api.canonApi, "byIngest").mockResolvedValue(jobReview([proposal("p1")]));
    const user = userEvent.setup();

    renderPage();
    await screen.findByTestId("review-filter-bar");

    await user.selectOptions(screen.getByLabelText(/filter by status/i), "pending");

    expect(replaceMock).toHaveBeenCalled();
    const lastUrl = replaceMock.mock.calls.at(-1)![0] as string;
    const params = new URLSearchParams(lastUrl.slice(1));
    expect(params.get("status")).toBe("pending");
    expect(params.get("scope")).toBe("ingest");
    // Deep-link param preserved
    expect(params.get("job")).toBe(JOB_ID);
  });

  it("applies deep-linked filters on load (?job=<id>&status=accepted)", async () => {
    searchParams = new URLSearchParams(`job=${JOB_ID}&status=accepted`);
    vi.spyOn(api.ingestApi, "listJobs").mockResolvedValue([job(JOB_ID)]);
    vi.spyOn(api.canonApi, "byIngest").mockResolvedValue(
      jobReview([proposal("p1")], [proposal("p2", "accepted")]),
    );

    renderPage();

    // Pending row filtered out by the deep-linked status filter; accepted shown
    expect(await screen.findByTestId("review-row-p2")).toBeInTheDocument();
    expect(screen.queryByTestId("review-row-p1")).not.toBeInTheDocument();
  });
});

describe("/forge/review — ingestion jobs scope (F1-4a, I-4)", () => {
  it("deep link ?job=<id> selects the ingest scope and loads that job", async () => {
    searchParams = new URLSearchParams(`job=${JOB_ID}`);
    vi.spyOn(api.ingestApi, "listJobs").mockResolvedValue([job(JOB_ID)]);
    const byIngestSpy = vi.spyOn(api.canonApi, "byIngest")
      .mockResolvedValue(jobReview([proposal("p1")]));

    renderPage();

    await waitFor(() => expect(byIngestSpy).toHaveBeenCalledWith(JOB_ID));
    expect((await screen.findAllByText("Statement p1")).length).toBeGreaterThan(0);
  });

  it("sends verdicts through canonApi.batchVerdicts", async () => {
    searchParams = new URLSearchParams(`job=${JOB_ID}`);
    vi.spyOn(api.ingestApi, "listJobs").mockResolvedValue([job(JOB_ID)]);
    vi.spyOn(api.canonApi, "byIngest").mockResolvedValue(jobReview([proposal("p1")]));
    const verdictSpy = vi.spyOn(api.canonApi, "batchVerdicts")
      .mockResolvedValue({ results: [], errors: [] });
    const user = userEvent.setup();

    renderPage();

    await user.click(await screen.findByTitle("Accept"));

    await waitFor(() =>
      expect(verdictSpy).toHaveBeenCalledWith([
        { proposal_id: "p1", decision: "accepted", reason: "Approved in Forge review" },
      ]),
    );
  });

  it("surfaces per-item batch failures", async () => {
    searchParams = new URLSearchParams(`job=${JOB_ID}`);
    vi.spyOn(api.ingestApi, "listJobs").mockResolvedValue([job(JOB_ID)]);
    vi.spyOn(api.canonApi, "byIngest")
      .mockResolvedValue(jobReview([proposal("p1"), proposal("p2")]));
    vi.spyOn(api.canonApi, "batchVerdicts").mockResolvedValue({
      results: [{
        proposal_id: "p1",
        status: "accepted",
        decision_metadata: { decided_by: "GM", decided_at: "", reason: "" },
      }],
      errors: [{ proposal_id: "p2", error: "Proposal already decided" }],
    });
    const user = userEvent.setup();

    renderPage();

    await user.click(await screen.findByRole("button", { name: /select visible \(2\)/i }));
    await user.click(screen.getByRole("button", { name: /accept selected/i }));
    await user.click(await screen.findByRole("button", { name: /confirm accept \(2\)/i }));

    expect(await screen.findByText(/1 accepted, 1 failed/i)).toBeInTheDocument();
  });

  it("commits accepted proposals via canonApi.commitByIngest", async () => {
    searchParams = new URLSearchParams(`job=${JOB_ID}`);
    vi.spyOn(api.ingestApi, "listJobs").mockResolvedValue([job(JOB_ID)]);
    vi.spyOn(api.canonApi, "byIngest")
      .mockResolvedValue(jobReview([], [proposal("p1", "accepted")]));
    const commitSpy = vi.spyOn(api.canonApi, "commitByIngest").mockResolvedValue({
      ingestion_job_id: JOB_ID,
      committed: 1,
      errors: [],
      status: "done",
    });
    const user = userEvent.setup();

    renderPage();

    await user.click(await screen.findByRole("button", { name: /commit 1 to canon/i }));

    await waitFor(() => expect(commitSpy).toHaveBeenCalledWith(JOB_ID));
    expect(await screen.findByText(/committed 1 proposals to canon/i)).toBeInTheDocument();
  });
});

describe("/forge/review — story scope (CF-8, F2-3)", () => {
  const stories = {
    stories: [{ id: STORY_ID, title: "Ashes of the Moon", story_type: "campaign" }],
    total: 1,
  };

  it("loads the story queue including the story-level no-scene lane", async () => {
    searchParams = new URLSearchParams("scope=story");
    vi.spyOn(api.storiesApi, "listStories").mockResolvedValue(stories);
    const queueSpy = vi.spyOn(api.canonApi, "storyQueue").mockResolvedValue(
      storyQueue([
        {
          scene_id: null,
          pending: [proposal("story-level")],
          accepted: [],
          rejected: [],
          by_change_type: { fact: 1 },
        },
      ]),
    );
    const user = userEvent.setup();

    renderPage();

    // wait for the stories query to populate the picker
    await screen.findByRole("option", { name: /ashes of the moon/i });
    await user.selectOptions(screen.getByLabelText(/^story$/i), STORY_ID);

    // only_pending=false so the status filter can reach decided items too
    await waitFor(() => expect(queueSpy).toHaveBeenCalledWith(STORY_ID, false));
    expect(await screen.findByTestId("review-row-story-level")).toBeInTheDocument();
  });

  it("applies verdicts to story proposals through the shared workbench", async () => {
    searchParams = new URLSearchParams("scope=story");
    vi.spyOn(api.storiesApi, "listStories").mockResolvedValue(stories);
    vi.spyOn(api.canonApi, "storyQueue").mockResolvedValue(
      storyQueue([
        {
          scene_id: "scene-1",
          pending: [proposal("p1")],
          accepted: [],
          rejected: [],
          by_change_type: { fact: 1 },
        },
      ]),
    );
    const verdictSpy = vi.spyOn(api.canonApi, "batchVerdicts")
      .mockResolvedValue({ results: [], errors: [] });
    const user = userEvent.setup();

    renderPage();

    await screen.findByRole("option", { name: /ashes of the moon/i });
    await user.selectOptions(screen.getByLabelText(/^story$/i), STORY_ID);
    await user.click(await screen.findByTitle("Accept"));

    await waitFor(() =>
      expect(verdictSpy).toHaveBeenCalledWith([
        { proposal_id: "p1", decision: "accepted", reason: "Approved in Forge review" },
      ]),
    );
  });
});
