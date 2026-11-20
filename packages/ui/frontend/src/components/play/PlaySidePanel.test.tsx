// @vitest-environment happy-dom
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { PlaySidePanel } from "./PlaySidePanel";

// The panel's children pull in large query trees — stub them so this test
// stays hermetic and only exercises the drawer/panel shell.
vi.mock("./CastPanel", () => ({ CastPanel: () => <div data-testid="cast-panel" /> }));
vi.mock("./CharacterPanel", () => ({
  CharacterPanel: () => <div data-testid="character-panel" />,
}));
vi.mock("./CombatPanel", () => ({ CombatPanel: () => <div data-testid="combat-panel" /> }));
vi.mock("./StoryPanel", () => ({ StoryPanel: () => <div data-testid="story-panel" /> }));
vi.mock("@/components/canon/CanonReviewPanel", () => ({
  CanonReviewPanel: () => <div data-testid="canon-panel" />,
}));

const baseProps = {
  open: false,
  onClose: vi.fn(),
  activeSession: null,
  sessionState: undefined,
  activeBenchmark: null,
  auditMeta: {},
  socialRead: {},
  relationshipSnapshot: {},
  socialDeltaEntries: [] as [string, number][],
  recapLines: [] as string[],
  castSpeaker: null,
  onSwitchSpeaker: vi.fn(),
  selectedCharacter: null,
  onSelectCharacter: vi.fn(),
  chatMode: "ic" as const,
  onChatModeChange: vi.fn(),
};

describe("PlaySidePanel", () => {
  it("stays hidden below xl when the drawer is closed", () => {
    render(<PlaySidePanel {...baseProps} />);
    const panel = screen.getByTestId("play-side-panel");
    expect(panel).toHaveAttribute("data-open", "false");
    expect(panel.className).toContain("hidden");
    expect(screen.queryByText(/session panels/i)).not.toBeInTheDocument();
  });

  it("renders the drawer chrome with a labelled close button when open", () => {
    const onClose = vi.fn();
    render(<PlaySidePanel {...baseProps} open={true} onClose={onClose} />);
    expect(screen.getByTestId("play-side-panel")).toHaveAttribute("data-open", "true");
    expect(screen.getByText(/session panels/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /close side panels/i }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("closes when the backdrop is clicked", () => {
    const onClose = vi.fn();
    const { container } = render(<PlaySidePanel {...baseProps} open={true} onClose={onClose} />);
    const backdrop = container.querySelector('[aria-hidden="true"]');
    expect(backdrop).not.toBeNull();
    fireEvent.click(backdrop!);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("renders the static session-context card", () => {
    render(<PlaySidePanel {...baseProps} />);
    expect(screen.getByText(/session context/i)).toBeInTheDocument();
    expect(screen.getByText(/create a session to bind it/i)).toBeInTheDocument();
    expect(screen.getByTestId("character-panel")).toBeInTheDocument();
  });
});
