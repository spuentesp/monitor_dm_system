// @vitest-environment happy-dom
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { PageError } from "./PageError";

describe("PageError", () => {
  it("renders the title and an alert role", () => {
    render(<PageError title="Boom" detail="it broke" />);
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByText("Boom")).toBeInTheDocument();
    expect(screen.getByText("it broke")).toBeInTheDocument();
  });

  it("reloads the window when the Reload button is clicked", () => {
    const reload = vi.fn();
    Object.defineProperty(window, "location", {
      value: { reload },
      writable: true,
    });
    render(<PageError title="Boom" />);
    fireEvent.click(screen.getByRole("button", { name: /reload/i }));
    expect(reload).toHaveBeenCalledOnce();
  });

  it("uses the default title when none is provided", () => {
    render(<PageError />);
    expect(screen.getByText(/Something went wrong/)).toBeInTheDocument();
  });
});
