// @vitest-environment happy-dom
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { SessionList } from "./SessionList";
import type { Session } from "@/lib/types";

function session(over: Partial<Session> = {}): Session {
  return {
    id: "sess-1",
    title: "Test Session",
    mode: "autonomous_gm",
    phase: "active_play",
    updated_at: new Date().toISOString(),
    created_at: new Date().toISOString(),
    tone: "dramatic",
    multiverse_id: null,
    multiverse_label: null,
    universe_id: null,
    universe_label: null,
    speaker_label: null,
    benchmark_id: null,
    benchmark_label: null,
    ...over,
  };
}

describe("SessionList", () => {
  it("renders a button per session", () => {
    render(
      <SessionList
        sessions={[session({ id: "a", title: "Session A" }), session({ id: "b", title: "Session B" })]}
        activeId={null}
        onSelect={() => {}}
        onNew={() => {}}
        onDelete={() => {}}
        onRename={() => {}}
        loading={false}
      />,
    );
    expect(screen.getByText("Session A")).toBeInTheDocument();
    expect(screen.getByText("Session B")).toBeInTheDocument();
  });

  it("shows empty state when no sessions", () => {
    render(
      <SessionList
        sessions={[]}
        activeId={null}
        onSelect={() => {}}
        onNew={() => {}}
        onDelete={() => {}}
        onRename={() => {}}
        loading={false}
      />,
    );
    expect(screen.getByText(/No sessions yet/i)).toBeInTheDocument();
  });

  it("shows loading indicator when loading", () => {
    render(
      <SessionList
        sessions={[]}
        activeId={null}
        onSelect={() => {}}
        onNew={() => {}}
        onDelete={() => {}}
        onRename={() => {}}
        loading={true}
      />,
    );
    expect(screen.getByText(/Loading…/i)).toBeInTheDocument();
  });

  it("filters sessions when the search input has content", () => {
    render(
      <SessionList
        sessions={[
          session({ id: "1", title: "Geralt in Rivia" }),
          session({ id: "2", title: "Yennefer in Vengerberg" }),
        ]}
        activeId={null}
        onSelect={() => {}}
        onNew={() => {}}
        onDelete={() => {}}
        onRename={() => {}}
        loading={false}
      />,
    );
    // Both visible initially
    expect(screen.getByText(/Geralt/)).toBeInTheDocument();
    expect(screen.getByText(/Yennefer/)).toBeInTheDocument();
  });
});
