// @vitest-environment happy-dom
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";

// Mock next/navigation so we can drive usePathname per test.
let mockPathname = "/";
vi.mock("next/navigation", () => ({
  usePathname: () => mockPathname,
}));

// Stub the footer widgets — they need react-query / world context.
vi.mock("@/components/WorldPicker", () => ({
  WorldPicker: () => <div data-testid="world-picker" />,
}));
vi.mock("@/components/ModeSwitcher", () => ({
  ModeSwitcher: () => <div data-testid="mode-switcher" />,
}));
vi.mock("@/components/ConnectionStatus", () => ({
  ConnectionStatus: () => <div data-testid="connection-status" />,
}));

import { Sidebar } from "./Sidebar";

function renderSidebar(pathname = "/") {
  mockPathname = pathname;
  return render(<Sidebar />);
}

describe("Sidebar nav groups (F1-1)", () => {
  it("renders the four groups: Modes, Forge, Query, System", () => {
    renderSidebar();
    for (const label of ["Modes", "Forge", "Query", "System"]) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
  });

  it("Modes group contains Play, GM Assistant and Characters", () => {
    renderSidebar();
    for (const label of ["Play", "GM Assistant", "Characters"]) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
  });

  it("Forge collapses to a single entry linking /forge", () => {
    renderSidebar();
    const forge = screen.getByRole("link", { name: /World Forge/ });
    expect(forge).toHaveAttribute("href", "/forge");
    // The old standalone authoring entries are gone from the sidebar.
    for (const gone of ["Worlds", "Snapshots", "Systems", "World Architect"]) {
      expect(screen.queryByRole("link", { name: gone })).not.toBeInTheDocument();
    }
  });

  it("Query group contains Search, Explorer and History", () => {
    renderSidebar();
    for (const label of ["Search", "Explorer", "History"]) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
  });

  it("highlights the Forge entry on nested forge routes", () => {
    renderSidebar("/forge/packs");
    const forge = screen.getByRole("link", { name: /World Forge/ });
    expect(forge).toHaveAttribute("aria-current", "page");
  });
});
