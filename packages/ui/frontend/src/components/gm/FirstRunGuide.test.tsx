// @vitest-environment happy-dom
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { FirstRunGuide, FirstUseTour, TOUR_DISMISS_KEY } from "./FirstRunGuide";

describe("FirstRunGuide (no-universe first run)", () => {
  it("walks through picking a world, a system and the recorder", () => {
    render(<FirstRunGuide />);

    expect(screen.getByTestId("first-run-guide")).toBeInTheDocument();
    expect(screen.getByText(/pick a world in the universe selector/i)).toBeInTheDocument();
    expect(screen.getByText(/choose the rpg system/i)).toBeInTheDocument();
    expect(screen.getByText(/session recorder/i)).toBeInTheDocument();

    const forgeLink = screen.getByRole("link", { name: /create a world in forge/i });
    expect(forgeLink).toHaveAttribute("href", "/forge");
  });
});

describe("FirstUseTour (dismissible)", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("mentions dice, rules lookup and the recorder", () => {
    render(<FirstUseTour />);
    const tour = screen.getByTestId("first-use-tour");
    expect(tour).toHaveTextContent(/dice roller/i);
    expect(tour).toHaveTextContent(/rules lookup/i);
    expect(tour).toHaveTextContent(/session recorder/i);
  });

  it("dismisses the card and remembers it in localStorage", async () => {
    const user = userEvent.setup();
    const { unmount } = render(<FirstUseTour />);
    expect(screen.getByTestId("first-use-tour")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Dismiss tour" }));
    expect(screen.queryByTestId("first-use-tour")).not.toBeInTheDocument();
    expect(window.localStorage.getItem(TOUR_DISMISS_KEY)).toBe("dismissed");

    // A fresh mount (next visit) stays dismissed.
    unmount();
    render(<FirstUseTour />);
    expect(screen.queryByTestId("first-use-tour")).not.toBeInTheDocument();
  });

  it("stays visible for this visit when storage is unavailable", async () => {
    const setItem = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("quota");
    });
    const user = userEvent.setup();
    render(<FirstUseTour />);

    await user.click(screen.getByRole("button", { name: "Dismiss tour" }));
    // Dismissal still applies in-memory even though persistence failed.
    expect(screen.queryByTestId("first-use-tour")).not.toBeInTheDocument();
    setItem.mockRestore();
  });
});
