// @vitest-environment happy-dom
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NPCCard } from "./NPCCard";
import type { NPC } from "@/lib/types";

function npc(over: Partial<NPC> = {}): NPC {
  return {
    id: "npc-1",
    name: "Geralt of Rivia",
    entity_type: "character",
    description: "A weathered witcher with white hair.",
    state_tags: [],
    canon_level: "draft",
    ...over,
  } as NPC;
}

describe("NPCCard", () => {
  it("renders the NPC name", () => {
    render(<NPCCard npc={npc()} onClick={() => {}} />);
    expect(screen.getByText("Geralt of Rivia")).toBeInTheDocument();
  });

  it("renders state tags as chips when present", () => {
    render(<NPCCard npc={npc({ state_tags: ["angry", "wounded"] })} onClick={() => {}} />);
    expect(screen.getByText("angry")).toBeInTheDocument();
    expect(screen.getByText("wounded")).toBeInTheDocument();
  });

  it("does not render state tags when state_tags is empty", () => {
    render(<NPCCard npc={npc({ state_tags: [] })} onClick={() => {}} />);
    expect(screen.queryByText("tag-dim")).not.toBeInTheDocument();
  });

  it("renders description when present", () => {
    render(<NPCCard npc={npc({ description: "A short tale" })} onClick={() => {}} />);
    expect(screen.getByText(/A short tale/)).toBeInTheDocument();
  });

  it("calls onClick when clicked", async () => {
    const onClick = vi.fn();
    const user = userEvent.setup();
    render(<NPCCard npc={npc()} onClick={onClick} />);
    await user.click(screen.getByRole("button"));
    expect(onClick).toHaveBeenCalledOnce();
  });

  it("has an accessible role=button", () => {
    render(<NPCCard npc={npc()} onClick={() => {}} />);
    expect(screen.getByRole("button")).toBeInTheDocument();
  });
});
