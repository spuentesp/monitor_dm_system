// @vitest-environment happy-dom
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AskTheWorldPanel } from "./AskTheWorldPanel";
import * as api from "@/lib/api";

beforeEach(() => {
  vi.restoreAllMocks();
  vi.spyOn(api.searchApi, "universeSearch").mockResolvedValue({
    query: "Who rules the drowned court?",
    collections_searched: ["entities"],
    total_results: 1,
    results: [
      {
        id: "e-1",
        collection: "entities",
        score: 0.91,
        payload: {},
        text: "The Eelmother rules the Drowned Court from her throne of chains.",
        entity_type: "character",
        universe_id: "u-1",
        story_id: null,
      },
    ],
  });
});

describe("AskTheWorldPanel", () => {
  it("asks a question against the selected universe and shows canon hits", async () => {
    const user = userEvent.setup();
    render(<AskTheWorldPanel universeId="u-1" />);

    await user.type(screen.getByPlaceholderText(/ask the world/i), "Who rules the drowned court?");
    await user.click(screen.getByRole("button", { name: /ask/i }));

    expect(api.searchApi.universeSearch).toHaveBeenCalledWith(
      "u-1",
      "Who rules the drowned court?",
      { limit: 5 },
    );
    expect(await screen.findByText(/Eelmother rules the Drowned Court/)).toBeInTheDocument();
    expect(screen.getByText("entities")).toBeInTheDocument();
  });

  it("prompts for a universe when none is selected", () => {
    render(<AskTheWorldPanel universeId={null} />);
    expect(screen.getByText(/select a universe/i)).toBeInTheDocument();
    expect(screen.queryByPlaceholderText(/ask the world/i)).not.toBeInTheDocument();
  });
});
