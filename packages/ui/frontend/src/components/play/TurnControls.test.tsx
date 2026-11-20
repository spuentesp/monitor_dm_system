// @vitest-environment happy-dom
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { TurnControls, findLastPlayerAction } from "./TurnControls";
import type { Message } from "@/lib/types";

function msg(over: Partial<Message>): Message {
  return {
    id: "m1",
    session_id: "s1",
    role: "player",
    content: "",
    timestamp: new Date().toISOString(),
    metadata: {},
    ...over,
  };
}

describe("findLastPlayerAction", () => {
  it("returns the most recent non-empty player message", () => {
    const messages = [
      msg({ id: "1", role: "gm", content: "You enter the tavern." }),
      msg({ id: "2", content: "I look around." }),
      msg({ id: "3", role: "gm", content: "Dusty." }),
      msg({ id: "4", content: "I sit down." }),
    ];
    expect(findLastPlayerAction(messages)).toBe("I sit down.");
  });

  it("skips dice-result player messages", () => {
    const messages = [
      msg({ id: "1", content: "I swing." }),
      msg({ id: "2", content: "🎲 stealth", metadata: { type: "dice_result" } }),
    ];
    expect(findLastPlayerAction(messages)).toBe("I swing.");
  });

  it("returns null when there is no player action yet", () => {
    expect(findLastPlayerAction([])).toBeNull();
    expect(findLastPlayerAction([msg({ id: "1", role: "gm", content: "Hello" })])).toBeNull();
    expect(
      findLastPlayerAction([msg({ id: "1", content: "   ", metadata: { type: "dice_result" } })]),
    ).toBeNull();
  });
});

describe("TurnControls", () => {
  it("renders nothing before the first player action", () => {
    const { container } = render(
      <TurnControls messages={[]} disabled={false} onRegenerate={vi.fn()} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it("regenerates by re-sending the last player action", () => {
    const onRegenerate = vi.fn();
    render(
      <TurnControls
        messages={[msg({ id: "1", content: "I draw my sword." })]}
        disabled={false}
        onRegenerate={onRegenerate}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /regenerate gm reply/i }));
    expect(onRegenerate).toHaveBeenCalledWith("I draw my sword.");
  });

  it("is disabled while a turn is in flight", () => {
    render(
      <TurnControls
        messages={[msg({ id: "1", content: "I draw my sword." })]}
        disabled={true}
        onRegenerate={vi.fn()}
      />,
    );
    expect(screen.getByRole("button", { name: /regenerate gm reply/i })).toBeDisabled();
  });

  it("does not render edit-last-turn or undo controls (no backend endpoints)", () => {
    render(
      <TurnControls
        messages={[msg({ id: "1", content: "I draw my sword." })]}
        disabled={false}
        onRegenerate={vi.fn()}
      />,
    );
    expect(screen.queryByRole("button", { name: /edit/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /undo/i })).not.toBeInTheDocument();
  });
});
