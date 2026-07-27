// @vitest-environment happy-dom
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ConsequenceBanner } from "./ConsequenceBanner";

describe("ConsequenceBanner", () => {
  it("renders nothing when no options are present", () => {
    const { container } = render(
      <ConsequenceBanner pending={{ options: [] }} disabled={false} onChoose={() => {}} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it("renders one button per option", () => {
    render(
      <ConsequenceBanner
        pending={{ options: ["Pay the toll", "Slip past unseen", "Demand passage"] }}
        disabled={false}
        onChoose={() => {}}
      />,
    );
    expect(screen.getByRole("button", { name: /Pay the toll/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Slip past unseen/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Demand passage/ })).toBeInTheDocument();
  });

  it("clicking an option fires onChoose with that string", async () => {
    const user = userEvent.setup();
    const onChoose = vi.fn();
    render(
      <ConsequenceBanner
        pending={{ options: ["Pay the toll", "Slip past unseen"] }}
        disabled={false}
        onChoose={onChoose}
      />,
    );

    await user.click(screen.getByRole("button", { name: /Slip past unseen/ }));
    expect(onChoose).toHaveBeenCalledWith("Slip past unseen");
  });

  it("disables all buttons when disabled=true", () => {
    render(
      <ConsequenceBanner
        pending={{ options: ["A", "B"] }}
        disabled
        onChoose={() => {}}
      />,
    );
    expect(screen.getByRole("button", { name: /A/ })).toBeDisabled();
    expect(screen.getByRole("button", { name: /B/ })).toBeDisabled();
  });

  it("renders the risk_preview when provided", () => {
    render(
      <ConsequenceBanner
        pending={{
          options: ["A"],
          risk_preview: "Either way, you draw the guard's attention",
        }}
        disabled={false}
        onChoose={() => {}}
      />,
    );
    expect(screen.getByText(/Either way, you draw the guard's attention/)).toBeInTheDocument();
  });

  it("caps the rendered options at 4 even if more are provided", () => {
    render(
      <ConsequenceBanner
        pending={{ options: ["A", "B", "C", "D", "E", "F"] }}
        disabled={false}
        onChoose={() => {}}
      />,
    );
    // A-E are visible, F is not (capped at 4).
    expect(screen.getByRole("button", { name: /^A$/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^D$/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^E$/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^F$/ })).not.toBeInTheDocument();
  });
});