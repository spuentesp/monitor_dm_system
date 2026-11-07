// @vitest-environment happy-dom
/** Held claims panel (I-17): a person accepts, edits or rejects claims review couldn't settle. */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ApiError, ingestApi } from "@/lib/api";
import type { HeldClaim } from "@/lib/types";
import { HeldClaimsPanel, refusalText } from "./HeldClaimsPanel";

const notify = vi.hoisted(() => vi.fn());
vi.mock("@/components/NotificationProvider", () => ({ useNotify: () => ({ notify }) }));

function claim(overrides: Partial<HeldClaim> = {}): HeldClaim {
  return {
    claim_id: "c1",
    kind: "rule",
    statement: "Roll two dice and keep the higher.",
    original_statement: "Roll two dice and keep the higher.",
    name: null,
    reason: "Unresolved contradiction: the book says both",
    page: 12,
    sources: [{ id: "s1", text: "Roll two dice, keep the higher one.", page: 12 }],
    conflicts: [{ claim_id: "c2", statement: "Roll one die." }],
    decision: null,
    ...overrides,
  };
}

function renderPanel() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <HeldClaimsPanel jobId="job-1" />
    </QueryClientProvider>,
  );
}

describe("HeldClaimsPanel", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("shows the claim, why it waits, its source and what it conflicts with", async () => {
    vi.spyOn(ingestApi, "listHeldClaims").mockResolvedValue([claim(), claim({ claim_id: "c3", decision: { claim_id: "c3", accepted: true, statement: "x", decided_at: "2026-11-05T00:00:00Z" } })]);
    renderPanel();
    expect(await screen.findByDisplayValue("Roll two dice and keep the higher.")).toBeTruthy();
    expect(screen.getByText(/Why it waits: Unresolved contradiction/)).toBeTruthy();
    expect(screen.getByText(/Roll two dice, keep the higher one\./)).toBeTruthy();
    expect(screen.getByText("Roll one die.")).toBeTruthy();
    expect(screen.getAllByTestId("held-claim")).toHaveLength(1);
    expect(screen.getByText(/1 claims to review\. 1 already decided\./)).toBeTruthy();
  });

  it("accepts with the edited wording", async () => {
    vi.spyOn(ingestApi, "listHeldClaims").mockResolvedValue([claim()]);
    const decide = vi.spyOn(ingestApi, "decideHeldClaim").mockResolvedValue({ claims_for_review: 0 });
    renderPanel();
    const box = await screen.findByLabelText("Claim wording");
    await userEvent.clear(box);
    await userEvent.type(box, "Roll two dice; keep the higher.");
    await userEvent.click(screen.getByRole("button", { name: /Accept/ }));
    await waitFor(() => expect(decide).toHaveBeenCalledWith("job-1", "c1", true, "Roll two dice; keep the higher."));
  });

  it("rejects without sending wording, and shows the server's refusal", async () => {
    vi.spyOn(ingestApi, "listHeldClaims").mockResolvedValue([claim()]);
    const decide = vi
      .spyOn(ingestApi, "decideHeldClaim")
      .mockRejectedValue(new ApiError(409, JSON.stringify({ detail: "The pack is applied." })));
    renderPanel();
    await userEvent.click(await screen.findByRole("button", { name: /Reject/ }));
    await waitFor(() => expect(decide).toHaveBeenCalledWith("job-1", "c1", false, undefined));
    await waitFor(() => expect(notify).toHaveBeenCalledWith("error", "The pack is applied."));
  });

  it("reads a refusal that isn't JSON", () => {
    expect(refusalText(new ApiError(500, "Server down"))).toBe("Server down");
  });
});
