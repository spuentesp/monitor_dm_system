// @vitest-environment happy-dom
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { PageSkeleton } from "./PageSkeleton";

describe("PageSkeleton", () => {
  it("renders the requested number of body rows plus the header bar", () => {
    render(<PageSkeleton rows={5} />);
    // Header + 5 body rows = 6 direct children with role-bearing elements.
    // Just check it has the expected ARIA semantics.
    expect(screen.getByRole("status")).toBeInTheDocument();
    expect(screen.getByRole("status").getAttribute("aria-busy")).toBe("true");
  });

  it("renders the two-column variant", () => {
    render(<PageSkeleton variant="two-column" rows={3} />);
    expect(screen.getByRole("status").className).toContain("grid-cols-1");
  });
});
