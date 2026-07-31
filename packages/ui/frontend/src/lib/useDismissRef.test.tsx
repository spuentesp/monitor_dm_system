// @vitest-environment happy-dom
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { useDismissRef } from "./useDismissRef";

function Popover({ onDismiss }: { onDismiss: () => void }) {
  const [open, setOpen] = useState(false);
  const ref = useDismissRef<HTMLDivElement>(() => setOpen(false), open);
  return (
    <div>
      <button onClick={() => setOpen((o) => !o)}>toggle</button>
      {open && (
        <div ref={ref} data-testid="popover">
          <button onClick={onDismiss}>inside action</button>
        </div>
      )}
      <button>outside</button>
    </div>
  );
}

describe("useDismissRef", () => {
  it("dismisses on outside mousedown", async () => {
    const user = userEvent.setup();
    render(<Popover onDismiss={vi.fn()} />);
    await user.click(screen.getByRole("button", { name: "toggle" }));
    expect(screen.getByTestId("popover")).toBeInTheDocument();
    fireEvent.mouseDown(screen.getByRole("button", { name: "outside" }));
    expect(screen.queryByTestId("popover")).not.toBeInTheDocument();
  });

  it("does not dismiss on inside mousedown", async () => {
    const user = userEvent.setup();
    render(<Popover onDismiss={vi.fn()} />);
    await user.click(screen.getByRole("button", { name: "toggle" }));
    fireEvent.mouseDown(screen.getByTestId("popover"));
    expect(screen.getByTestId("popover")).toBeInTheDocument();
  });

  it("dismisses on Escape", async () => {
    const user = userEvent.setup();
    render(<Popover onDismiss={vi.fn()} />);
    await user.click(screen.getByRole("button", { name: "toggle" }));
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByTestId("popover")).not.toBeInTheDocument();
  });

  it("does not listen while inactive", () => {
    function Probe({ active, onDismiss }: { active: boolean; onDismiss: () => void }) {
      const ref = useDismissRef<HTMLDivElement>(onDismiss, active);
      return <div ref={ref}>anchored</div>;
    }
    const onDismiss = vi.fn();
    render(<Probe active={false} onDismiss={onDismiss} />);
    fireEvent.keyDown(document, { key: "Escape" });
    fireEvent.mouseDown(document.body);
    expect(onDismiss).not.toHaveBeenCalled();
  });
});
