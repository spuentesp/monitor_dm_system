// @vitest-environment happy-dom
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { SessionRecorder } from "./SessionRecorder";
import { chatApi, gmApi } from "@/lib/api";

// P1.1 — live contradiction alerts in the Session Recorder. The check is
// advisory: it fires after an entry is logged and renders an amber alert card
// under the matching transcript entry only when the backend flags a conflict.

vi.mock("@/lib/api", () => ({
  chatApi: {
    listSessions: vi.fn(),
    getMessages: vi.fn(),
    sendMessage: vi.fn(),
    createSession: vi.fn(),
    endScene: vi.fn(),
    wrapUp: vi.fn(),
  },
  storiesApi: { listThreads: vi.fn() },
  gmApi: { checkEntryContradiction: vi.fn(), captureInsights: vi.fn() },
}));

const RECORDING = {
  id: "rec-1",
  title: "Table log — today",
  mode: "gm_assistant",
  universe_id: "u-1",
  updated_at: new Date().toISOString(),
};

const ALERT = {
  fact_a: "Established canon: the king is dead",
  fact_b: "Logged entry: The king greeted the party at the gate",
  severity: "medium",
  explanation: "The king cannot greet anyone: canon says he is dead.",
  suggestion: "Review this entry against canon before canonizing.",
};

const EMPTY_INSIGHT = {
  participants: [],
  locations: [],
  candidate_facts: [],
  advances_thread: "",
};

const INSIGHT = {
  participants: ["Mira"],
  locations: ["The Sunken Chapel"],
  candidate_facts: ["the key is now with Mira"],
  advances_thread: "The sealed door",
};

/** After sendMessage, logEntry invalidates the messages query — so the
 * refetch must return the persisted entry for the transcript (and any alert
 * card beneath it) to stay on screen. */
function stubTranscript(text: string) {
  vi.mocked(chatApi.getMessages).mockResolvedValue([
    {
      id: "m-1",
      session_id: RECORDING.id,
      role: "player",
      content: text,
      timestamp: new Date().toISOString(),
      metadata: {},
    },
  ] as never);
}

function renderRecorder() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <SessionRecorder universeId="u-1" />
    </QueryClientProvider>,
  );
}

async function logEntry(text: string) {
  const textarea = await screen.findByPlaceholderText(/Log what happened/);
  await userEvent.type(textarea, text);
  await userEvent.click(screen.getByRole("button", { name: "Log entry" }));
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(chatApi.listSessions).mockResolvedValue([RECORDING] as never);
  vi.mocked(chatApi.getMessages).mockResolvedValue([] as never);
  vi.mocked(chatApi.sendMessage).mockResolvedValue({} as never);
  vi.mocked(gmApi.captureInsights).mockResolvedValue(EMPTY_INSIGHT);
});

describe("SessionRecorder live contradiction alerts (P1.1)", () => {
  it("renders an amber alert card under the entry when a contradiction is found", async () => {
    const text = "The king greeted the party at the gate";
    stubTranscript(text);
    vi.mocked(gmApi.checkEntryContradiction).mockResolvedValue({ alert: ALERT });
    renderRecorder();

    await logEntry(text);

    const card = await screen.findByTestId("contradiction-alert");
    expect(card).toHaveTextContent("Possible canon conflict.");
    expect(card).toHaveTextContent(ALERT.explanation);
    expect(card.className).toContain("amber");
    expect(gmApi.checkEntryContradiction).toHaveBeenCalledWith("u-1", text);
  });

  it("renders no alert card when the entry is canon-consistent", async () => {
    const text = "The party camped under the stars";
    stubTranscript(text);
    vi.mocked(gmApi.checkEntryContradiction).mockResolvedValue({ alert: null });
    renderRecorder();

    await logEntry(text);

    // Wait until the check round-tripped before asserting absence.
    await waitFor(() => expect(gmApi.checkEntryContradiction).toHaveBeenCalled());
    await new Promise((r) => setTimeout(r, 20));
    expect(screen.queryByTestId("contradiction-alert")).toBeNull();
    expect(screen.getByText(text)).toBeInTheDocument();
  });

  it("skips the check for entries under 12 characters", async () => {
    vi.mocked(gmApi.checkEntryContradiction).mockResolvedValue({ alert: ALERT });
    renderRecorder();

    await logEntry("Mira left.");

    await waitFor(() => expect(chatApi.sendMessage).toHaveBeenCalled());
    // Give the (non-)fired check a beat to resolve if it had fired.
    await new Promise((r) => setTimeout(r, 20));
    expect(gmApi.checkEntryContradiction).not.toHaveBeenCalled();
    expect(screen.queryByTestId("contradiction-alert")).toBeNull();
  });
});

describe("SessionRecorder per-entry capture insights (P1.2)", () => {
  it("renders participant/location chips and candidate facts under the entry", async () => {
    const text = "Mira pocketed the key beneath the chapel";
    stubTranscript(text);
    vi.mocked(gmApi.checkEntryContradiction).mockResolvedValue({ alert: null });
    vi.mocked(gmApi.captureInsights).mockResolvedValue(INSIGHT);
    renderRecorder();

    await logEntry(text);

    const card = await screen.findByTestId("capture-insights");
    expect(card).toHaveTextContent("Mira");
    expect(card).toHaveTextContent("The Sunken Chapel");
    expect(card).toHaveTextContent("Candidate facts");
    expect(card).toHaveTextContent("the key is now with Mira");
    expect(card).toHaveTextContent("Advances: The sealed door");
    expect(gmApi.captureInsights).toHaveBeenCalledWith("u-1", text);
  });

  it("renders insights alongside a contradiction alert for the same entry", async () => {
    const text = "The king greeted the party at the gate";
    stubTranscript(text);
    vi.mocked(gmApi.checkEntryContradiction).mockResolvedValue({ alert: ALERT });
    vi.mocked(gmApi.captureInsights).mockResolvedValue(INSIGHT);
    renderRecorder();

    await logEntry(text);

    expect(await screen.findByTestId("contradiction-alert")).toBeInTheDocument();
    expect(await screen.findByTestId("capture-insights")).toBeInTheDocument();
  });

  it("renders nothing when the insight is empty", async () => {
    const text = "The party camped under the stars";
    stubTranscript(text);
    vi.mocked(gmApi.checkEntryContradiction).mockResolvedValue({ alert: null });
    vi.mocked(gmApi.captureInsights).mockResolvedValue(EMPTY_INSIGHT);
    renderRecorder();

    await logEntry(text);

    await waitFor(() => expect(gmApi.captureInsights).toHaveBeenCalled());
    await new Promise((r) => setTimeout(r, 20));
    expect(screen.queryByTestId("capture-insights")).toBeNull();
    expect(screen.getByText(text)).toBeInTheDocument();
  });

  it("swallows insight failures — logging is never broken", async () => {
    const text = "The party moved on at dawn";
    stubTranscript(text);
    vi.mocked(gmApi.checkEntryContradiction).mockResolvedValue({ alert: null });
    vi.mocked(gmApi.captureInsights).mockRejectedValue(new Error("backend down"));
    renderRecorder();

    await logEntry(text);

    await waitFor(() => expect(gmApi.captureInsights).toHaveBeenCalled());
    await new Promise((r) => setTimeout(r, 20));
    expect(screen.queryByTestId("capture-insights")).toBeNull();
    expect(screen.getByText(text)).toBeInTheDocument();
  });
});

describe("SessionRecorder wrap-up (P1.3/P1.4)", () => {
  it("appends a '· wrapped up' marker to wrapped-up recordings in the dropdown", async () => {
    vi.mocked(chatApi.listSessions).mockResolvedValue([
      { ...RECORDING, id: "rec-open", title: "Table log — open" },
      {
        ...RECORDING,
        id: "rec-done",
        title: "Table log — done",
        wrapped_up_at: new Date().toISOString(),
      },
    ] as never);
    renderRecorder();

    const done = (await screen.findByRole("option", {
      name: /Table log — done/,
    })) as HTMLOptionElement;
    expect(done.textContent).toContain("· wrapped up");

    const open = (await screen.findByRole("option", {
      name: /Table log — open/,
    })) as HTMLOptionElement;
    expect(open.textContent).not.toContain("wrapped up");
  });

  it("offers a 'Wrap up session' action that opens the wrap-up modal", async () => {
    vi.mocked(chatApi.wrapUp).mockResolvedValue({
      recap: "The party sealed the chapel door.",
      accepted: 1,
      rejected: 0,
      pending: 0,
      canon_items: [],
      open_threads: [],
      next_prep: null,
    } as never);
    renderRecorder();

    await userEvent.click(
      await screen.findByRole("button", { name: /Wrap up session/ }),
    );
    expect(await screen.findByTestId("wrap-up-recap")).toHaveTextContent(
      "The party sealed the chapel door.",
    );
    expect(chatApi.wrapUp).toHaveBeenCalledWith("rec-1");
  });
});
