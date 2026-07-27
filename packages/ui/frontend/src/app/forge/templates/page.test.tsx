// @vitest-environment happy-dom
/**
 * Smoke test for the /forge/templates page (F3-2e):
 * renders the entity-template section by default and switches to random tables.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import * as api from "@/lib/api";
import ForgeTemplatesPage from "./page";

const UNIVERSE_ID = "11111111-1111-1111-1111-111111111111";

vi.mock("@/lib/world-context", () => ({
  useWorldContext: () => ({
    multiverseId: null,
    universeId: UNIVERSE_ID,
    universeLabel: "Test World",
    setWorld: vi.fn(),
    clearWorld: vi.fn(),
  }),
}));

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ForgeTemplatesPage />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.restoreAllMocks();
  vi.spyOn(api.templatesApi, "list").mockResolvedValue({
    templates: [],
    total: 0,
    limit: 50,
    offset: 0,
  });
  vi.spyOn(api.randomTablesApi, "list").mockResolvedValue({
    tables: [],
    total: 0,
    limit: 50,
    offset: 0,
  });
});

describe("/forge/templates page", () => {
  it("renders the entity-template section by default", async () => {
    renderPage();
    expect(screen.getByRole("button", { name: /entity templates/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /random tables/i })).toBeInTheDocument();
    // TemplateBrowser toolbar is mounted
    expect(await screen.findByRole("button", { name: /new template/i })).toBeInTheDocument();
  });

  it("switches to the random-tables section", async () => {
    const user = userEvent.setup();
    renderPage();
    await user.click(screen.getByRole("button", { name: /random tables/i }));
    expect(await screen.findByRole("button", { name: /new table/i })).toBeInTheDocument();
  });
});
