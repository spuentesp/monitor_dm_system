// @vitest-environment happy-dom
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { WorldContextProvider } from "@/lib/world-context";
import { entitiesApi, universesApi } from "@/lib/api";
import type { Universe } from "@/lib/types";
import GMAssistantPage from "./page";

// Deep link straight to a universe so the stepper's persistence has a key.
vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams("universe=u-1"),
}));

// The wrap-up flow itself is exercised by WrapUpModal.test.tsx; here we only
// verify the stepper opens and closes it.
vi.mock("@/components/gm/WrapUpModal", () => ({
  WrapUpModal: ({ onClose }: { onClose: () => void }) => (
    <div data-testid="wrap-modal">
      <button type="button" onClick={onClose}>
        Close wrap
      </button>
    </div>
  ),
}));

const UNIVERSE: Universe = {
  id: "u-1",
  name: "Alpha World",
  multiverse_id: "mv-1",
  genre: null,
  description: null,
  default_game_system_id: null,
  tags: [],
  is_active: true,
  entity_count: 0,
  session_count: 0,
  created_at: "2026-01-01T00:00:00Z",
};

const RECORDING = {
  id: "rec-1",
  title: "Table log — today",
  mode: "gm_assistant",
  universe_id: "u-1",
  story_id: "st-1",
  updated_at: "2026-11-20T00:00:00Z",
};

function stubFetch(sessions: unknown[]) {
  globalThis.fetch = vi.fn((input: RequestInfo | URL) => {
    const url =
      typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    let body = "[]";
    if (url.includes("canon-queue")) body = JSON.stringify({ scenes: [] });
    else if (url.includes("/chat") && !url.includes("/messages")) body = JSON.stringify(sessions);
    else if (url.includes("/messages")) body = "[]";
    return Promise.resolve(
      new Response(body, { status: 200, headers: { "Content-Type": "application/json" } }),
    );
  }) as unknown as typeof fetch;
}

function mockApis() {
  vi.spyOn(universesApi, "listMultiverses").mockResolvedValue([]);
  vi.spyOn(universesApi, "listUniverses").mockResolvedValue([UNIVERSE]);
  vi.spyOn(universesApi, "getUniverse").mockResolvedValue(UNIVERSE);
  vi.spyOn(entitiesApi, "listSystems").mockResolvedValue([]);
}

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
  window.localStorage.clear();
  mockApis();
  stubFetch([RECORDING]);
});

describe("GM Assistant Prep → Run → Wrap-up stepper (UX-5)", () => {
  it("starts on Run, persists Prep per universe, and restores it on reload", async () => {
    const user = userEvent.setup();
    const { unmount } = renderPage();

    // Run is the default step (recorder-first).
    expect(screen.getByTestId("gm-step-run")).toHaveAttribute("aria-current", "step");

    // Choose Prep — persisted under this universe's key.
    await user.click(screen.getByTestId("gm-step-prep"));
    expect(screen.getByTestId("gm-step-prep")).toHaveAttribute("aria-current", "step");
    expect(window.localStorage.getItem("monitor.gm.step.u-1")).toBe("prep");

    // Prep narrows the tools: tonight/combat/… tabs disappear, Prep shows.
    expect(screen.queryAllByRole("button", { name: /^combat$/i })).toHaveLength(0);
    expect(screen.getAllByText(/pick a story and click generate/i).length).toBeGreaterThan(0);

    // "Reload": a fresh mount restores the remembered step.
    unmount();
    renderPage();
    await waitFor(() =>
      expect(screen.getByTestId("gm-step-prep")).toHaveAttribute("aria-current", "step"),
    );
  });

  it("Run shows the recorder and full tool set again after Prep", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByTestId("gm-step-prep"));
    await user.click(screen.getByTestId("gm-step-run"));

    expect(screen.getByTestId("gm-step-run")).toHaveAttribute("aria-current", "step");
    expect(window.localStorage.getItem("monitor.gm.step.u-1")).toBe("run");
    // The full tool tab set is back (Combat is a run-only view in this test).
    expect((await screen.findAllByRole("button", { name: /^combat$/i })).length).toBeGreaterThan(0);
  });

  it("Wrap-up opens the wrap-up flow and closing it returns to the previous step", async () => {
    const user = userEvent.setup();
    renderPage();

    // Open Wrap-up from Prep: closing must land back on Prep, not Run.
    await user.click(screen.getByTestId("gm-step-prep"));
    expect(window.localStorage.getItem("monitor.gm.step.u-1")).toBe("prep");

    const wrap = screen.getByTestId("gm-step-wrap");
    await waitFor(() => expect(wrap).not.toBeDisabled());
    await user.click(wrap);
    expect(await screen.findByTestId("wrap-modal")).toBeInTheDocument();
    expect(screen.getByTestId("gm-step-wrap")).toHaveAttribute("aria-current", "step");
    // Wrap never overwrites the persisted resting step.
    expect(window.localStorage.getItem("monitor.gm.step.u-1")).toBe("prep");

    await user.click(screen.getByRole("button", { name: "Close wrap" }));
    expect(screen.queryByTestId("wrap-modal")).not.toBeInTheDocument();
    expect(screen.getByTestId("gm-step-prep")).toHaveAttribute("aria-current", "step");
    expect(window.localStorage.getItem("monitor.gm.step.u-1")).toBe("prep");
  });

  it("Wrap-up without any recording explains what to do first", async () => {
    stubFetch([]);
    const user = userEvent.setup();
    renderPage();

    const wrap = screen.getByTestId("gm-step-wrap");
    await waitFor(() => expect(wrap).not.toBeDisabled());
    await user.click(wrap);

    const empty = await screen.findByTestId("gm-wrap-empty");
    expect(empty).toHaveTextContent(/log at least one entry/i);
    await user.click(screen.getByRole("button", { name: "Close" }));
    expect(screen.queryByTestId("gm-wrap-empty")).not.toBeInTheDocument();
    expect(screen.getByTestId("gm-step-run")).toHaveAttribute("aria-current", "step");
  });
});
