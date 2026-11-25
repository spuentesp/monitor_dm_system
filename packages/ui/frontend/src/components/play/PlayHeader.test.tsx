// @vitest-environment happy-dom
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { PlayHeader } from "./PlayHeader";
import type { ChatSessionState, Session } from "@/lib/types";

function renderHeader(ui: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>{ui}</QueryClientProvider>,
  );
}

const baseProps = {
  activeSessionId: null,
  activeSession: null,
  sessionState: undefined,
  messageCount: 0,
  chatMode: "ic" as const,
  onChatModeChange: vi.fn(),
  hasSelectedCharacter: false,
  onPatchTone: vi.fn(),
  onPatchRollModel: vi.fn(),
  onSkipPreplay: vi.fn(),
  skipPending: false,
  onBeginStory: vi.fn(),
  beginPending: false,
  endingScene: false,
  onEndScene: vi.fn(),
  onToggleSessions: vi.fn(),
  sessionsOpen: false,
  onTogglePanels: vi.fn(),
  panelsOpen: false,
};

const session = {
  id: "s-1",
  title: "The Ashen Road",
  mode: "autonomous_gm",
  tone: "grim",
  phase: "active_play",
  play_mode: "dice_game_system",
  roll_model: "tap",
  story_id: null,
} as Session;

describe("PlayHeader", () => {
  it("renders the idle title without a session", () => {
    renderHeader(<PlayHeader {...baseProps} />);
    expect(screen.getByText("Select or create a session")).toBeInTheDocument();
  });

  it("renders session meta, tone and end-scene controls", () => {
    renderHeader(<PlayHeader {...baseProps} activeSessionId="s-1" activeSession={session} messageCount={12} />);
    expect(screen.getByText("The Ashen Road")).toBeInTheDocument();
    expect(screen.getByText(/12 messages/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /change session tone/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /change dice roll model/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /end scene/i })).toBeInTheDocument();
  });

  it("shows skip-to-play during pre-play phases", () => {
    renderHeader(
      <PlayHeader
        {...baseProps}
        activeSessionId="s-1"
        activeSession={{ ...session, phase: "session_zero" } as Session}
      />,
    );
    expect(screen.getByRole("button", { name: /use defaults & begin/i })).toBeInTheDocument();
  });

  it("hides skip-to-play once in active play", () => {
    renderHeader(<PlayHeader {...baseProps} activeSessionId="s-1" activeSession={session} />);
    expect(screen.queryByRole("button", { name: /use defaults & begin/i })).not.toBeInTheDocument();
  });

  it("toggles the phone drawers with labelled buttons", () => {
    const onToggleSessions = vi.fn();
    const onTogglePanels = vi.fn();
    renderHeader(
      <PlayHeader
        {...baseProps}
        onToggleSessions={onToggleSessions}
        onTogglePanels={onTogglePanels}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /show sessions/i }));
    fireEvent.click(screen.getByRole("button", { name: /show side panels/i }));
    expect(onToggleSessions).toHaveBeenCalledTimes(1);
    expect(onTogglePanels).toHaveBeenCalledTimes(1);
  });

  it("renders the begin-story button when Session Zero awaits confirmation", () => {
    const sessionState = {
      session: { phase: "session_zero" },
      latest_gm_metadata: { type: "story_agreements_summary" },
    } as unknown as ChatSessionState;
    renderHeader(
      <PlayHeader {...baseProps} activeSessionId="s-1" activeSession={session} sessionState={sessionState} />,
    );
    expect(screen.getByRole("button", { name: /begin story/i })).toBeInTheDocument();
  });
});
