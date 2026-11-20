// @vitest-environment happy-dom
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { gmApi } from "@/lib/api";
import { DiceRoller, isValidDiceExpression } from "./DiceRoller";

function renderDice() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <DiceRoller />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.restoreAllMocks();
});

describe("DiceRoller (server-authoritative)", () => {
  it("validates expressions client-side", () => {
    expect(isValidDiceExpression("2d6+3")).toBe(true);
    expect(isValidDiceExpression("d20")).toBe(true);
    expect(isValidDiceExpression("garbage")).toBe(false);
    expect(isValidDiceExpression("0d6")).toBe(false);
    expect(isValidDiceExpression("101d6")).toBe(false);
    expect(isValidDiceExpression("1d1")).toBe(false);
  });

  it("renders the SERVER roll result, never a client-side total", async () => {
    const spy = vi.spyOn(gmApi, "rollDice").mockResolvedValue({
      total: 18,
      rolls: [15],
      expression: "1d20+3",
      kept_rolls: [15],
      modifier: 3,
    });
    const user = userEvent.setup();
    renderDice();

    const input = screen.getByPlaceholderText("e.g. 2d6+3");
    await user.clear(input);
    await user.type(input, "1d20+3");
    await user.keyboard("{Enter}");

    await waitFor(() => expect(spy).toHaveBeenCalledWith("1d20+3"));
    expect(await screen.findByText("18")).toBeInTheDocument();
    expect(screen.getByText("[15] +3")).toBeInTheDocument();
  });

  it("never calls the API for an invalid expression", async () => {
    const spy = vi.spyOn(gmApi, "rollDice").mockResolvedValue({
      total: 1,
      rolls: [1],
      expression: "1d20",
      kept_rolls: [1],
      modifier: 0,
    });
    const user = userEvent.setup();
    renderDice();

    const input = screen.getByPlaceholderText("e.g. 2d6+3");
    await user.clear(input);
    await user.type(input, "garbage");
    await user.keyboard("{Enter}");

    expect(spy).not.toHaveBeenCalled();
  });

  it("marks history entries for j/k navigation", async () => {
    vi.spyOn(gmApi, "rollDice").mockResolvedValue({
      total: 7,
      rolls: [7],
      expression: "1d8",
      kept_rolls: [7],
      modifier: 0,
    });
    const user = userEvent.setup();
    renderDice();

    await user.click(screen.getByText("d8"));
    await user.click(screen.getByText("d6"));

    await waitFor(() =>
      expect(document.querySelectorAll("[data-gm-entry]").length).toBe(2),
    );
  });
});
