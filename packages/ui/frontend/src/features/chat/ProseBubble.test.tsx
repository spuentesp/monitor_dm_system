// @vitest-environment happy-dom
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { ProseBubble, splitNarrationBlocks } from "./ProseBubble";

describe("splitNarrationBlocks", () => {
  it("returns the whole string unmarked when there are no OOC markers", () => {
    expect(splitNarrationBlocks("You draw your rivet gun.")).toEqual([
      { ooc: false, text: "You draw your rivet gun." },
    ]);
  });

  it("splits a single OOC block", () => {
    expect(splitNarrationBlocks("((No roll needed for that.))")).toEqual([
      { ooc: true, text: "No roll needed for that." },
    ]);
  });

  it("splits mixed narration and a trailing OOC aside", () => {
    const text = "You draw your rivet gun. ((This is a hard-mode encounter.))";
    expect(splitNarrationBlocks(text)).toEqual([
      { ooc: false, text: "You draw your rivet gun." },
      { ooc: true, text: "This is a hard-mode encounter." },
    ]);
  });

  it("splits a leading OOC aside followed by narration", () => {
    const text = "((By the way, no dice here.)) You step into the corridor.";
    expect(splitNarrationBlocks(text)).toEqual([
      { ooc: true, text: "By the way, no dice here." },
      { ooc: false, text: "You step into the corridor." },
    ]);
  });

  it("handles an OOC block spanning newlines", () => {
    const text = "((This is a longer\naside that spans\nmultiple lines.))";
    expect(splitNarrationBlocks(text)).toEqual([
      { ooc: true, text: "This is a longer\naside that spans\nmultiple lines." },
    ]);
  });

  it("drops whitespace-only segments", () => {
    expect(splitNarrationBlocks("((note))   \n   the rest")).toEqual([
      { ooc: true, text: "note" },
      { ooc: false, text: "the rest" },
    ]);
  });

  it("tolerates triple parens (models occasionally emit (((...))) )", () => {
    const text = "((( The intent is sound, but roll your Tech for me next turn. )))";
    expect(splitNarrationBlocks(text)).toEqual([
      { ooc: true, text: "The intent is sound, but roll your Tech for me next turn." },
    ]);
  });

  it("returns an empty array for an empty string", () => {
    expect(splitNarrationBlocks("")).toEqual([]);
  });
});

describe("ProseBubble", () => {
  it("renders plain narration text", () => {
    render(<ProseBubble>Welcome, traveler.</ProseBubble>);
    expect(screen.getByText("Welcome, traveler.")).toBeInTheDocument();
  });

  it("renders *action* text as italic", () => {
    render(<ProseBubble>{"*the door creaks open*"}</ProseBubble>);
    const em = screen.getByText("the door creaks open");
    expect(em.tagName).toBe("EM");
  });

  it("renders an OOC aside in a distinct block, separate from narration", () => {
    render(
      <ProseBubble>
        {"You draw your rivet gun. ((This is a hard-mode encounter.))"}
      </ProseBubble>,
    );
    expect(screen.getByText("You draw your rivet gun.")).toBeInTheDocument();
    expect(screen.getByText("This is a hard-mode encounter.")).toBeInTheDocument();
    expect(screen.getByText("OOC")).toBeInTheDocument();
  });
});
