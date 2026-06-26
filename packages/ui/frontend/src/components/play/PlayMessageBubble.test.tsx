// @vitest-environment happy-dom
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { PlayMessageBubble } from "./PlayMessageBubble";
import type { Message } from "@/lib/types";
import type { ThinkingTrace } from "@/features/chat";

function msg(over: Partial<Message> = {}): Message {
  return {
    id: "m1",
    session_id: "s1",
    role: "gm",
    content: "Hello world",
    timestamp: new Date().toISOString(),
    metadata: {},
    ...over,
  };
}

describe("PlayMessageBubble", () => {
  it("renders GM content as ProseBubble text", () => {
    render(<PlayMessageBubble msg={msg({ content: "Welcome, traveler." })} />);
    expect(screen.getByText("Welcome, traveler.")).toBeInTheDocument();
  });

  it("renders a ThinkingBubble when metadata.thinking is set", () => {
    render(
      <PlayMessageBubble
        msg={msg({
          content: "Final prose.",
          metadata: { thinking: "Reasoning happened here." },
        })}
      />,
    );
    expect(screen.getByText("Reasoning happened here.")).toBeInTheDocument();
  });

  it("renders a live ThinkingBubble when msg.thinking is set (streaming)", () => {
    const trace: ThinkingTrace = {
      message_id: "m1",
      text: "Live chain of thought",
      streaming: true,
    };
    render(<PlayMessageBubble msg={msg({ content: "...", thinking: trace })} />);
    expect(screen.getByText("Live chain of thought")).toBeInTheDocument();
    expect(screen.getByText(/Reasoning…/)).toBeInTheDocument();
  });

  it("does NOT render a ThinkingBubble for player messages with thinking metadata", () => {
    render(
      <PlayMessageBubble
        msg={msg({
          role: "player",
          content: "I attack the goblin.",
          metadata: { thinking: "should not show" },
        })}
      />,
    );
    expect(screen.queryByText(/Reasoning/)).not.toBeInTheDocument();
  });

  it("renders DiceResultCard when metadata.roll_detail is present (GM)", () => {
    render(
      <PlayMessageBubble
        msg={msg({
          content: "You strike true.",
          metadata: {
            type: "scene_turn",
            success_level: "success",
            roll_detail: { spec: "1d20+3", total: 18, rolls: [15] },
          },
        })}
      />,
    );
    // The dice face total (18) appears once; the spec appears in both
    // header and footer of the card, so use getAllByText.
    expect(screen.getByText("18")).toBeInTheDocument();
    expect(screen.getAllByText("1d20+3").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/success/i)).toBeInTheDocument();
  });

  it("renders the streaming cursor when msg.streaming is a string", () => {
    render(<PlayMessageBubble msg={msg({ content: "", streaming: "Streami" })} />);
    // The streaming text appears in the bubble.
    expect(screen.getByText("Streami")).toBeInTheDocument();
  });

  it("renders a system message with system styling", () => {
    render(
      <PlayMessageBubble msg={msg({ role: "system", content: "Session paused." })} />,
    );
    expect(screen.getByText("Session paused.")).toBeInTheDocument();
  });

  it("renders social_read chip when GM metadata has social continuity data", () => {
    render(
      <PlayMessageBubble
        msg={msg({
          content: "The captain nods.",
          metadata: {
            social_read: { stance_after: "neutral", reason: "you said nothing rude" },
          },
        })}
      />,
    );
    expect(screen.getByText(/Social continuity/i)).toBeInTheDocument();
    expect(screen.getByText(/neutral/)).toBeInTheDocument();
  });
});