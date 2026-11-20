// @vitest-environment happy-dom
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { TurnWaitBar } from "./TurnWaitBar";

describe("TurnWaitBar", () => {
  it("renders nothing when no turn is active", () => {
    const { container } = render(
      <TurnWaitBar waiting={false} isWaitingForGm={true} seconds={0} onCancel={vi.fn()} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it("shows the GM-is-thinking state with elapsed seconds", () => {
    render(<TurnWaitBar waiting={true} isWaitingForGm={true} seconds={7} onCancel={vi.fn()} />);
    const bar = screen.getByTestId("turn-wait-bar");
    expect(bar).toHaveTextContent("GM is thinking");
    expect(bar).toHaveTextContent("7s");
    expect(bar).toHaveAttribute("aria-live", "polite");
  });

  it("shows the writing state once tokens are streaming", () => {
    render(<TurnWaitBar waiting={true} isWaitingForGm={false} seconds={12} onCancel={vi.fn()} />);
    expect(screen.getByTestId("turn-wait-bar")).toHaveTextContent("GM is writing");
  });

  it("invokes onCancel from the labelled cancel button", () => {
    const onCancel = vi.fn();
    render(<TurnWaitBar waiting={true} isWaitingForGm={true} seconds={1} onCancel={onCancel} />);
    fireEvent.click(screen.getByRole("button", { name: /cancel waiting for the gm/i }));
    expect(onCancel).toHaveBeenCalledTimes(1);
  });
});
