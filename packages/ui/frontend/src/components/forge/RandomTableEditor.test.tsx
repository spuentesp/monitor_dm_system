// @vitest-environment happy-dom
/**
 * Tests for the RandomTableBrowser create flow (F3-2d):
 * - "New Table" opens the create modal
 * - submit calls randomTablesApi.create and drops into table-edit mode
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import * as api from "@/lib/api";
import type { RandomTable } from "@/lib/types";
import { RandomTableBrowser } from "./RandomTableEditor";

const UNIVERSE_ID = "11111111-1111-1111-1111-111111111111";

function makeTable(over: Partial<RandomTable> = {}): RandomTable {
  return {
    table_id: "33333333-3333-3333-3333-333333333333",
    universe_id: UNIVERSE_ID,
    name: "Tavern Rumors",
    description: "",
    table_type: "rumor",
    dice_formula: "1d20",
    weighted: false,
    entries: [
      { min_roll: 1, max_roll: 20, weight: null, value: "New entry", subtable_id: null, conditions: null },
    ],
    source_id: null,
    game_system_id: null,
    created_at: "2026-07-24T00:00:00Z",
    updated_at: null,
    ...over,
  };
}

function renderBrowser() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <RandomTableBrowser universeId={UNIVERSE_ID} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.restoreAllMocks();
  vi.spyOn(api.randomTablesApi, "list").mockResolvedValue({
    tables: [],
    total: 0,
    limit: 50,
    offset: 0,
  });
});

describe("RandomTableBrowser create", () => {
  it("creates a table and drops into table-edit mode", async () => {
    const created = makeTable();
    const createSpy = vi.spyOn(api.randomTablesApi, "create").mockResolvedValue(created);
    const user = userEvent.setup();
    renderBrowser();

    await user.click(await screen.findByRole("button", { name: /new table/i }));
    expect(await screen.findByText("New Random Table", { selector: "h2" })).toBeInTheDocument();

    await user.type(screen.getByPlaceholderText("e.g., Tavern Rumors"), "Tavern Rumors");
    await user.click(screen.getByRole("button", { name: /create table/i }));

    await waitFor(() => expect(createSpy).toHaveBeenCalledOnce());
    const payload = createSpy.mock.calls[0][0];
    expect(payload.name).toBe("Tavern Rumors");
    expect(payload.universe_id).toBe(UNIVERSE_ID);
    expect(payload.entries.length).toBeGreaterThanOrEqual(1);

    // Drops into the table editor for the freshly created table
    expect(await screen.findByText(/Entries \(1\)/)).toBeInTheDocument();
    expect(screen.getByDisplayValue("Tavern Rumors")).toBeInTheDocument();
  });

  it("requires a name before submitting", async () => {
    const createSpy = vi.spyOn(api.randomTablesApi, "create").mockResolvedValue(makeTable());
    const user = userEvent.setup();
    renderBrowser();

    await user.click(await screen.findByRole("button", { name: /new table/i }));
    await user.click(await screen.findByRole("button", { name: /create table/i }));

    expect(await screen.findByText("Name is required")).toBeInTheDocument();
    expect(createSpy).not.toHaveBeenCalled();
  });
});
