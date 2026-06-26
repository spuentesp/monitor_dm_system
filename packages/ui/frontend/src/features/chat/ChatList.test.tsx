// @vitest-environment happy-dom
import { describe, it, expect, vi, beforeAll } from "vitest";
import { render, screen } from "@testing-library/react";
import { ChatList } from "./ChatList";
import type { Message } from "@/lib/types";

// react-virtuoso needs ResizeObserver + IntersectionObserver in happy-dom.
beforeAll(() => {
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver;
  globalThis.IntersectionObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
    takeRecords() { return []; }
    root = null;
    rootMargin = "";
    thresholds = [];
  } as unknown as typeof IntersectionObserver;
});

// Virtuoso depends on ResizeObserver / IntersectionObserver for sizing.
// happy-dom doesn't ship them by default — stub a no-op implementation.
beforeAll(() => {
  class StubResizeObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
  (globalThis as unknown as { ResizeObserver: typeof StubResizeObserver }).ResizeObserver = StubResizeObserver;
  class StubIntersectionObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
    takeRecords() {
      return [];
    }
  }
  (globalThis as unknown as { IntersectionObserver: typeof StubIntersectionObserver }).IntersectionObserver = StubIntersectionObserver;
  // getBoundingClientRect returns zeros — Virtuoso falls back to defaults.
  if (!Element.prototype.getBoundingClientRect) {
    Element.prototype.getBoundingClientRect = function () {
      return { top: 0, bottom: 0, left: 0, right: 0, width: 0, height: 0, x: 0, y: 0, toJSON: () => ({}) } as DOMRect;
    };
  }
});

function msg(over: Partial<Message> = {}): Message {
  return {
    id: "m",
    session_id: "s",
    role: "gm",
    content: "",
    timestamp: new Date().toISOString(),
    metadata: {},
    ...over,
  };
}

describe("ChatList", () => {
  it("renders a renderBubble call per message", () => {
    const renderBubble = vi.fn((m: Message) => <div data-testid={`bubble-${m.id}`}>{m.content}</div>);
    render(
      <ChatList
        messages={[msg({ id: "a", content: "Hello" }), msg({ id: "b", content: "World" })]}
        streamingMsg={null}
        isTyping={false}
        sendFailure={null}
        pendingDiceRequest={null}
        renderBubble={renderBubble}
        onDiceResult={() => {}}
      />,
    );
    expect(screen.getByTestId("bubble-a")).toBeInTheDocument();
    expect(screen.getByTestId("bubble-b")).toBeInTheDocument();
    // React 19 may re-render items (initialItemCount, ResizeObserver
    // observations, strict mode). Just verify both messages rendered.
    const calledIds = renderBubble.mock.calls.map((c) => c[0]?.id).filter(Boolean);
    expect(calledIds).toContain("a");
    expect(calledIds).toContain("b");
  });

  it("synthesizes a streaming bubble at the end when streamingMsg is set", () => {
    const renderBubble = vi.fn((m: Message & { streaming?: string }) => (
      <div data-testid={`bubble-${m.id}`}>{m.streaming ?? m.content}</div>
    ));
    render(
      <ChatList
        messages={[msg({ id: "a", content: "Old" })]}
        streamingMsg={{ id: "live", text: "Streaming…" }}
        isTyping={false}
        sendFailure={null}
        pendingDiceRequest={null}
        renderBubble={renderBubble}
        onDiceResult={() => {}}
      />,
    );
    expect(screen.getByTestId("bubble-a")).toHaveTextContent("Old");
    expect(screen.getByTestId("bubble-live")).toHaveTextContent("Streaming…");
    // Three calls: original + the synthetic streaming bubble. (Virtuoso
    // may invoke itemContent a few times for measurement; assert at-least.)
    expect(renderBubble.mock.calls.length).toBeGreaterThanOrEqual(2);
  });

  it("shows emptyState when messages list is empty and no streaming state", () => {
    render(
      <ChatList
        messages={[]}
        streamingMsg={null}
        isTyping={false}
        sendFailure={null}
        pendingDiceRequest={null}
        renderBubble={() => <div />}
        onDiceResult={() => {}}
        emptyState={<div data-testid="empty">Tell the GM something</div>}
      />,
    );
    expect(screen.getByTestId("empty")).toBeInTheDocument();
  });

  it("renders the sendFailure card when sendFailure is set", () => {
    render(
      <ChatList
        messages={[]}
        streamingMsg={null}
        isTyping={false}
        sendFailure={{ text: "attack", detail: "rate-limited" }}
        pendingDiceRequest={null}
        renderBubble={() => <div />}
        onDiceResult={() => {}}
        onRetry={() => {}}
        onDismissFailure={() => {}}
      />,
    );
    expect(screen.getByText(/Turn didn/)).toBeInTheDocument();
    expect(screen.getByText(/rate-limited/)).toBeInTheDocument();
  });

  it("renders DiceRollPrompt when pendingDiceRequest is set", () => {
    render(
      <ChatList
        messages={[]}
        streamingMsg={null}
        isTyping={false}
        sendFailure={null}
        pendingDiceRequest={{ spec: "1d20+3", reason: "Strength check" }}
        renderBubble={() => <div />}
        onDiceResult={() => {}}
      />,
    );
    expect(screen.getByText(/Roll Required/)).toBeInTheDocument();
    expect(screen.getByText("Strength check")).toBeInTheDocument();
  });
});