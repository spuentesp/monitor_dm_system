// @vitest-environment happy-dom
/**
 * ArchitectMessageBubble tests (F2-1 wave 2):
 * - derived coverage_summary / priority_gaps metadata is visibly rendered
 *   (FORGE_EXPANSION.md §2 finding: previously computed but never rendered)
 * - priority-gap chips reuse the status idiom and suggest a composer prompt
 */

import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ArchitectMessageBubble } from "./ArchitectMessageBubble";
import type { Message } from "@/lib/types";

function msg(over: Partial<Message> = {}): Message {
  return {
    id: "m1",
    session_id: "s1",
    role: "gm",
    content: "I added the Iron Brotherhood to Aethoria.",
    timestamp: new Date().toISOString(),
    metadata: {},
    ...over,
  };
}

const ARCHITECT_META = {
  type: "world_architect",
  committed: 1,
  coverage_summary: "Current world coverage includes 2 entities, 1 axioms, and 0 lore facts.",
  priority_gaps: [
    {
      area: "Power structures",
      priority: 2,
      suggestion: "Define the factions, courts, houses, or institutions that hold power.",
      example_prompt: "The dominant factions are ____ because ____.",
    },
    {
      area: "World rules",
      priority: 4,
      suggestion: "Clarify the core axiom that governs magic, technology, faith, or survival.",
      example_prompt: "In this world, it is always true that ____.",
    },
  ],
};

describe("ArchitectMessageBubble — coverage surfacing", () => {
  it("renders the coverage summary and priority gap chips", () => {
    render(<ArchitectMessageBubble msg={msg({ metadata: ARCHITECT_META })} />);

    expect(screen.getByText("Coverage gaps")).toBeInTheDocument();
    expect(
      screen.getByText(/Current world coverage includes 2 entities/),
    ).toBeInTheDocument();
    expect(screen.getByText("Power structures")).toBeInTheDocument();
    expect(screen.getByText("World rules")).toBeInTheDocument();
  });

  it("clicking a priority gap chip suggests its example prompt", async () => {
    const onSuggest = vi.fn();
    const user = userEvent.setup();
    render(<ArchitectMessageBubble msg={msg({ metadata: ARCHITECT_META })} onSuggest={onSuggest} />);

    await user.click(screen.getByText("World rules"));

    expect(onSuggest).toHaveBeenCalledWith("In this world, it is always true that ____.");
  });

  it("does not render the coverage card for player messages", () => {
    render(
      <ArchitectMessageBubble
        msg={msg({ role: "player", content: "Add a faction.", metadata: ARCHITECT_META })}
      />,
    );
    expect(screen.queryByText("Coverage gaps")).not.toBeInTheDocument();
  });

  it("renders no coverage card when the metadata has neither summary nor gaps", () => {
    render(
      <ArchitectMessageBubble msg={msg({ metadata: { type: "world_architect", committed: 2 } })} />,
    );
    expect(screen.queryByText("Coverage gaps")).not.toBeInTheDocument();
  });
});
