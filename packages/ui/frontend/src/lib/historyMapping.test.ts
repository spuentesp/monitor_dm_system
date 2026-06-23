import { describe, it, expect } from "vitest";
import { Plus, Pencil, Trash2, Link2, Tag } from "lucide-react";
import { changeIcon, changeColor } from "./historyMapping";

describe("changeIcon", () => {
  it("maps creation/addition to Plus", () => {
    expect(changeIcon("created_entity")).toBe(Plus);
    expect(changeIcon("relationship_added")).toBe(Plus);
  });

  it("maps deletion/removal to Trash2", () => {
    expect(changeIcon("deleted_fact")).toBe(Trash2);
    expect(changeIcon("tag_removed")).toBe(Trash2);
  });

  it("maps relationships to Link2 and state tags to Tag", () => {
    expect(changeIcon("relationship_updated")).toBe(Link2);
    expect(changeIcon("state_tag_changed")).toBe(Tag);
  });

  it("falls back to Pencil for plain updates", () => {
    expect(changeIcon("updated_entity")).toBe(Pencil);
  });
});

describe("changeColor", () => {
  it("greens creates, reds deletes, ambers retcons, cyans the rest", () => {
    expect(changeColor("created_entity")).toBe("text-emerald-400");
    expect(changeColor("deleted_entity")).toBe("text-rose-400");
    expect(changeColor("retcon_applied")).toBe("text-amber-400");
    expect(changeColor("updated_entity")).toBe("text-cyan-400");
  });

  it("prioritises add/remove over retcon (addition check runs first)", () => {
    expect(changeColor("added")).toBe("text-emerald-400");
  });
});
