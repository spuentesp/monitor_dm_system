// @vitest-environment happy-dom
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { DifficultyBadge } from "./DifficultyBadge";
import type { EncounterDifficulty } from "@/lib/types";

function difficulty(over: Partial<EncounterDifficulty> = {}): EncounterDifficulty {
  return {
    label: "deadly",
    rationale: "Deadly for a level-3 party of 4: 168 threat against 96 party resources (1.75x).",
    threat: 168,
    party_budget: 96,
    ratio: 1.75,
    basis: "generic",
    details: { foe_count: 8 },
    ...over,
  };
}

describe("DifficultyBadge (CF-13)", () => {
  it("shows the label", () => {
    render(<DifficultyBadge difficulty={difficulty({ label: "hard" })} />);
    expect(screen.getByText("hard")).toBeInTheDocument();
  });

  it("shows the ratio", () => {
    render(<DifficultyBadge difficulty={difficulty({ ratio: 1.75 })} />);
    expect(screen.getByText("1.75x")).toBeInTheDocument();
  });

  it("shows the rationale so the GM can check the arithmetic", () => {
    render(<DifficultyBadge difficulty={difficulty()} />);
    expect(screen.getByText(/168 threat against 96 party resources/)).toBeInTheDocument();
  });

  it("omits the ratio when there is none", () => {
    render(<DifficultyBadge difficulty={difficulty({ label: "unrated", ratio: null })} />);
    expect(screen.getByText("unrated")).toBeInTheDocument();
    expect(screen.queryByText(/x$/)).not.toBeInTheDocument();
  });

  it("carries the rationale as a tooltip", () => {
    render(<DifficultyBadge difficulty={difficulty()} />);
    expect(screen.getByTestId("difficulty-badge")).toHaveAttribute(
      "title",
      expect.stringContaining("Deadly for a level-3 party of 4"),
    );
  });
});
