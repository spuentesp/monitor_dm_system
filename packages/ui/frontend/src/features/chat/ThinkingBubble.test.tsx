// @vitest-environment happy-dom
import { describe, it, expect } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ThinkingBubble } from "./ThinkingBubble";
import type { ThinkingTrace } from "./types";

function makeTrace(over: Partial<ThinkingTrace> = {}): ThinkingTrace {
  return {
    message_id: "m1",
    text: "the captain's posture suggests unease",
    streaming: false,
    ...over,
  };
}

describe("ThinkingBubble", () => {
  it("renders nothing when text is empty", () => {
    const { container } = render(<ThinkingBubble trace={makeTrace({ text: "" })} />);
    expect(container.firstChild).toBeNull();
  });

  it("renders the trace header with 'Reasoning…' label while streaming", () => {
    render(<ThinkingBubble trace={makeTrace({ streaming: true })} />);
    expect(screen.getByText(/Reasoning…/)).toBeInTheDocument();
  });

  it("renders the trace header with 'Reasoning' label when not streaming", () => {
    render(<ThinkingBubble trace={makeTrace({ streaming: false })} />);
    // Header has "Reasoning" without the ellipsis; check exact match.
    expect(screen.getByText(/^Reasoning$/)).toBeInTheDocument();
  });

  it("shows trace text in the body when expanded", () => {
    render(<ThinkingBubble trace={makeTrace({ streaming: true, text: "Detailed chain of thought" })} />);
    expect(screen.getByTestId("thinking-body")).toHaveTextContent("Detailed chain of thought");
  });

  it("toggles expanded/collapsed on header click", async () => {
    const user = userEvent.setup();
    const trace = makeTrace({ streaming: false, text: "Hidden text" });
    render(<ThinkingBubble trace={trace} />);

    // After streaming ends with defaultExpanded undefined, the bubble
    // starts collapsed — so the body is NOT mounted.
    expect(screen.queryByTestId("thinking-body")).not.toBeInTheDocument();

    // Click the header to expand.
    await user.click(screen.getByRole("button"));
    expect(screen.getByTestId("thinking-body")).toBeInTheDocument();

    // Click again to collapse. The body unmounts after the framer-motion
    // exit animation (~150ms), so use waitFor.
    await user.click(screen.getByRole("button"));
    await waitFor(() =>
      expect(screen.queryByTestId("thinking-body")).not.toBeInTheDocument(),
    );
  });

  it("body stays mounted while streaming=true even after a user click (live > toggle)", async () => {
    const user = userEvent.setup();
    const trace = makeTrace({ streaming: true, text: "Live text" });
    render(<ThinkingBubble trace={trace} />);

    expect(screen.getByTestId("thinking-body")).toBeInTheDocument();

    // User clicks — but the body should remain visible because the trace
    // is still streaming. This is intentional UX: don't let a user
    // accidentally hide reasoning that's actively arriving.
    await user.click(screen.getByRole("button"));
    // Give React a tick to process the state update.
    await waitFor(() => expect(screen.getByTestId("thinking-body")).toBeInTheDocument());
  });

  it("respects defaultExpanded override", () => {
    const trace = makeTrace({ streaming: false, text: "Always shown" });
    render(<ThinkingBubble trace={trace} defaultExpanded />);
    expect(screen.getByTestId("thinking-body")).toHaveTextContent("Always shown");
  });

  it("shows a preview snippet in the header when collapsed", () => {
    render(
      <ThinkingBubble
        trace={makeTrace({ streaming: false, text: "This is a long piece of reasoning that should be truncated in the header preview" })}
      />,
    );
    // The first 60 chars appear in the header preview line.
    expect(screen.getByText(/This is a long piece of reasoning that should be trunc/)).toBeInTheDocument();
  });
});