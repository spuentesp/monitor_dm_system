// @vitest-environment happy-dom
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {
  GmStepper,
  gmStepStorageKey,
  readStoredGmStep,
  writeStoredGmStep,
  type GmStep,
} from "./GmStepper";

describe("GmStepper", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("renders Prep, Run and Wrap-up with the current step marked aria-current", () => {
    const { rerender } = render(<GmStepper step="run" onStepChange={() => {}} />);
    expect(screen.getByTestId("gm-step-prep")).toBeInTheDocument();
    expect(screen.getByTestId("gm-step-run")).toBeInTheDocument();
    expect(screen.getByTestId("gm-step-wrap")).toBeInTheDocument();
    expect(screen.getByTestId("gm-step-run")).toHaveAttribute("aria-current", "step");
    expect(screen.getByTestId("gm-step-prep")).not.toHaveAttribute("aria-current");

    rerender(<GmStepper step="prep" onStepChange={() => {}} />);
    expect(screen.getByTestId("gm-step-prep")).toHaveAttribute("aria-current", "step");
    expect(screen.getByTestId("gm-step-run")).not.toHaveAttribute("aria-current");
  });

  it("reports clicks through onStepChange", async () => {
    const onChange = vi.fn<(s: GmStep) => void>();
    const user = userEvent.setup();
    render(<GmStepper step="run" onStepChange={onChange} />);

    await user.click(screen.getByTestId("gm-step-prep"));
    expect(onChange).toHaveBeenCalledWith("prep");
    await user.click(screen.getByTestId("gm-step-wrap"));
    expect(onChange).toHaveBeenCalledWith("wrap");
  });

  it("disables Wrap-up until a universe is selected", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<GmStepper step="run" onStepChange={onChange} wrapDisabled />);

    const wrap = screen.getByTestId("gm-step-wrap");
    expect(wrap).toBeDisabled();
    await user.click(wrap);
    expect(onChange).not.toHaveBeenCalled();
  });
});

describe("per-universe step persistence", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("round-trips prep/run per universe and never stores wrap", () => {
    writeStoredGmStep("u-1", "prep");
    writeStoredGmStep("u-2", "run");
    writeStoredGmStep("u-3", "wrap");

    expect(readStoredGmStep("u-1")).toBe("prep");
    expect(readStoredGmStep("u-2")).toBe("run");
    expect(readStoredGmStep("u-3")).toBeNull(); // wrap is transient
    expect(readStoredGmStep(null)).toBeNull();
    expect(window.localStorage.getItem(gmStepStorageKey("u-3"))).toBeNull();
  });

  it("ignores corrupt stored values and storage failures", () => {
    window.localStorage.setItem(gmStepStorageKey("u-1"), "bogus");
    expect(readStoredGmStep("u-1")).toBeNull();

    const setItem = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("quota");
    });
    expect(() => writeStoredGmStep("u-1", "prep")).not.toThrow();
    setItem.mockRestore();
  });
});
