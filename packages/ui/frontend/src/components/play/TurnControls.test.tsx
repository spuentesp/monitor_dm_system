// @vitest-environment happy-dom
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { TurnControls, findLastPlayerAction, hasPlayerMessage } from "./TurnControls";
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

function renderControls(over: Partial<Parameters<typeof TurnControls>[0]> = {}) {
  const props = {
    messages: [msg({ id: "1", content: "I draw my sword." })],
    disabled: false,
    onUndo: vi.fn(),
    onEditLast: vi.fn(),
    onRegenerate: vi.fn(),
    ...over,
  };
  render(<TurnControls {...props} />);
  return props;
}

describe("findLastPlayerAction", () => {
  it("returns the final player message's text", () => {
    const messages = [
      msg({ id: "1", role: "gm", content: "You enter the tavern." }),
      msg({ id: "2", content: "I look around." }),
      msg({ id: "3", role: "gm", content: "Dusty." }),
      msg({ id: "4", content: "I sit down." }),
    ];
    expect(findLastPlayerAction(messages)).toBe("I sit down.");
  });

  it("returns null when the final player message is a dice result", () => {
    // Rewind excises the FINAL exchange — a dice display text must not be
    // handed to edit/regenerate (its roll metadata wouldn't survive).
    const messages = [
      msg({ id: "1", content: "I swing." }),
      msg({ id: "2", content: "🎲 stealth", metadata: { type: "dice_result" } }),
    ];
    expect(findLastPlayerAction(messages)).toBeNull();
  });

  it("returns null when the final player message is a roll request", () => {
    const messages = [
      msg({ id: "1", content: "I swing." }),
      msg({ id: "2", content: "🎲 stealth…", metadata: { type: "roll_request" } }),
    ];
    expect(findLastPlayerAction(messages)).toBeNull();
  });

  it("returns null when there is no player message yet", () => {
    expect(findLastPlayerAction([])).toBeNull();
    expect(findLastPlayerAction([msg({ id: "1", role: "gm", content: "Hello" })])).toBeNull();
    expect(
      findLastPlayerAction([msg({ id: "1", content: "   ", metadata: { type: "dice_result" } })]),
    ).toBeNull();
  });
});

describe("hasPlayerMessage", () => {
  it("is true only once a player message exists", () => {
    expect(hasPlayerMessage([])).toBe(false);
    expect(hasPlayerMessage([msg({ id: "1", role: "gm", content: "Hi" })])).toBe(false);
    expect(hasPlayerMessage([msg({ id: "1", content: "Hi" })])).toBe(true);
  });
});

describe("TurnControls", () => {
  it("renders nothing before the first player message (nothing to rewind)", () => {
    const { container } = render(
      <TurnControls
        messages={[]}
        disabled={false}
        onUndo={vi.fn()}
        onEditLast={vi.fn()}
        onRegenerate={vi.fn()}
      />,
    );
    expect(container.firstChild).toBeNull();
  });

  it("renders undo, edit and regenerate once a player message exists", () => {
    renderControls();
    expect(screen.getByRole("button", { name: /undo last turn/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /edit last turn/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /regenerate gm reply/i })).toBeInTheDocument();
  });

  it("shows only Undo when the final player message is a dice result", () => {
    renderControls({
      messages: [
        msg({ id: "1", content: "I draw my sword." }),
        msg({ id: "2", content: "🎲 stealth", metadata: { type: "dice_result" } }),
        msg({ id: "3", role: "gm", content: "You slip into shadow." }),
      ],
    });
    expect(screen.getByRole("button", { name: /undo last turn/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /edit last turn/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /regenerate gm reply/i })).not.toBeInTheDocument();
  });

  it("undo invokes onUndo with no arguments", () => {
    const props = renderControls();
    fireEvent.click(screen.getByRole("button", { name: /undo last turn/i }));
    expect(props.onUndo).toHaveBeenCalledTimes(1);
    expect(props.onUndo).toHaveBeenCalledWith();
  });

  it("edit hands the last player action to onEditLast for composer pre-fill", () => {
    const props = renderControls();
    fireEvent.click(screen.getByRole("button", { name: /edit last turn/i }));
    expect(props.onEditLast).toHaveBeenCalledWith("I draw my sword.");
  });

  it("regenerate hands the last player action to onRegenerate (rewind + resend)", () => {
    const props = renderControls();
    fireEvent.click(screen.getByRole("button", { name: /regenerate gm reply/i }));
    expect(props.onRegenerate).toHaveBeenCalledWith("I draw my sword.");
  });

  it("disables all three controls while a turn is in flight", () => {
    renderControls({ disabled: true });
    expect(screen.getByRole("button", { name: /undo last turn/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /edit last turn/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /regenerate gm reply/i })).toBeDisabled();
  });
});
