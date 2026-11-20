// @vitest-environment happy-dom
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {
  useGmShortcuts,
  focusFirstVisible,
  moveGmEntry,
  type GmShortcutHandlers,
} from "./useGmShortcuts";

function Harness({ handlers }: { handlers: GmShortcutHandlers }) {
  useGmShortcuts(handlers);
  return (
    <div>
      <button type="button">outside-button</button>
      <input data-testid="text-input" />
      <textarea data-testid="text-area" />
      <div data-testid="entry-1" data-gm-entry>
        first entry
      </div>
      <div data-testid="entry-2" data-gm-entry>
        second entry
      </div>
    </div>
  );
}

describe("useGmShortcuts", () => {
  it("fires r and n outside of form fields", async () => {
    const onRoll = vi.fn();
    const onNewNote = vi.fn();
    const user = userEvent.setup();
    render(<Harness handlers={{ onRoll, onNewNote }} />);

    await user.keyboard("r");
    expect(onRoll).toHaveBeenCalledTimes(1);
    await user.keyboard("n");
    expect(onNewNote).toHaveBeenCalledTimes(1);
  });

  it("ignores shortcuts while typing in inputs and textareas", async () => {
    const onRoll = vi.fn();
    const onNewNote = vi.fn();
    const user = userEvent.setup();
    render(<Harness handlers={{ onRoll, onNewNote }} />);

    const input = screen.getByTestId("text-input");
    await user.click(input);
    await user.keyboard("rn");
    expect(onRoll).not.toHaveBeenCalled();
    expect(onNewNote).not.toHaveBeenCalled();
    expect((input as HTMLInputElement).value).toBe("rn");

    const textarea = screen.getByTestId("text-area");
    await user.click(textarea);
    await user.keyboard("r");
    expect(onRoll).not.toHaveBeenCalled();
  });

  it("ignores modifier combos", async () => {
    const onRoll = vi.fn();
    const user = userEvent.setup();
    render(<Harness handlers={{ onRoll }} />);

    await user.keyboard("{Control>}r{/Control}");
    expect(onRoll).not.toHaveBeenCalled();
  });

  it("j/k walks the entries (next/prev)", async () => {
    const user = userEvent.setup();
    render(<Harness handlers={{}} />);

    const first = screen.getByTestId("entry-1");
    const second = screen.getByTestId("entry-2");

    await user.keyboard("j");
    expect(first).toHaveAttribute("data-gm-entry-active", "true");
    expect(second).not.toHaveAttribute("data-gm-entry-active");

    await user.keyboard("j");
    expect(first).not.toHaveAttribute("data-gm-entry-active");
    expect(second).toHaveAttribute("data-gm-entry-active", "true");

    await user.keyboard("k");
    expect(first).toHaveAttribute("data-gm-entry-active", "true");
    expect(second).not.toHaveAttribute("data-gm-entry-active");

    // k at the top clamps instead of wrapping.
    await user.keyboard("k");
    expect(first).toHaveAttribute("data-gm-entry-active", "true");
  });
});

describe("focusFirstVisible", () => {
  it("focuses the first visible match (or the first match as a fallback)", () => {
    render(
      <div>
        <input data-testid="focus-target" />
      </div>,
    );
    expect(focusFirstVisible('[data-testid="focus-target"]')).toBeTypeOf("boolean");
    expect(document.activeElement).toBe(screen.getByTestId("focus-target"));
  });

  it("returns false when nothing matches", () => {
    expect(focusFirstVisible('[data-testid="does-not-exist"]')).toBe(false);
  });
});

describe("moveGmEntry", () => {
  it("is a no-op without entries", () => {
    expect(() => moveGmEntry(1)).not.toThrow();
    expect(() => moveGmEntry(-1)).not.toThrow();
  });
});
