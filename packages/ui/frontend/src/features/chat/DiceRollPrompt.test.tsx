// @vitest-environment happy-dom
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { DiceRollPrompt } from "./DiceRollPrompt";

const request = { spec: "1d20+1", reason: "STR check" };

describe("DiceRollPrompt", () => {
  it("offers only the server roll in tap mode", () => {
    const onServerRoll = vi.fn();
    render(
      <DiceRollPrompt request={request as never} onResult={vi.fn()} onServerRoll={onServerRoll} rollModel="tap" />,
    );

    expect(screen.queryByRole("spinbutton")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /roll 1d20\+1/i }));
    expect(onServerRoll).toHaveBeenCalledWith("1d20+1", "STR check");
  });

  it("offers only hand entry in manual mode", () => {
    const onResult = vi.fn();
    render(<DiceRollPrompt request={request as never} onResult={onResult} rollModel="manual" />);

    expect(screen.queryByRole("button", { name: /roll 1d20\+1/i })).toBeNull();
    fireEvent.change(screen.getByRole("spinbutton"), { target: { value: "15" } });
    fireEvent.click(screen.getByRole("button", { name: "Use" }));
    expect(onResult).toHaveBeenCalledWith("1d20+1", 15, [], "STR check");
  });
});
