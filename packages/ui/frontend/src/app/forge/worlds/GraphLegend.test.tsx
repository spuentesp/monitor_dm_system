// @vitest-environment happy-dom
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { GraphLegend } from "./GraphLegend";

describe("GraphLegend", () => {
  it("renders a list of node kinds", () => {
    render(<GraphLegend />);
    expect(screen.getByText(/Character/)).toBeInTheDocument();
    expect(screen.getByText(/Universe/)).toBeInTheDocument();
    expect(screen.getByText(/Faction/)).toBeInTheDocument();
  });

  it("contains all 9 kind labels", () => {
    render(<GraphLegend />);
    for (const label of ["Multiverse", "Universe", "Character", "Location", "Faction", "Concept", "Axiom", "Lore", "Rule"]) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
  });
});
