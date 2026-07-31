// @vitest-environment happy-dom
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";

// Mock next/navigation so we can drive usePathname per test.
let mockPathname = "/";
vi.mock("next/navigation", () => ({
  usePathname: () => mockPathname,
}));

vi.mock("@/components/ConnectionStatus", () => ({
  ConnectionStatus: () => <div data-testid="connection-status" />,
}));

import { Sidebar } from "./Sidebar";

function renderSidebar(pathname = "/") {
  mockPathname = pathname;
  return render(<Sidebar />);
}

describe("Sidebar two-tier nav", () => {
  it("renders the three tiers: Lobby, Workbench, Configuration", () => {
    renderSidebar();
    expect(screen.getByText("Lobby")).toBeInTheDocument();
    expect(screen.getByText("Workbench")).toBeInTheDocument();
    // "Configuration" appears as both the tier label and its single nav item.
    expect(screen.getAllByText("Configuration").length).toBeGreaterThanOrEqual(2);
    for (const gone of ["Modes", "Forge", "Query", "System"]) {
      expect(screen.queryByText(gone)).not.toBeInTheDocument();
    }
  });

  it("Lobby group contains Campaigns (/) and Light RP (/light-rp)", () => {
    renderSidebar();
    expect(screen.getByRole("link", { name: /Campaigns/ })).toHaveAttribute("href", "/");
    expect(screen.getByRole("link", { name: /Light RP/ })).toHaveAttribute("href", "/light-rp");
  });

  it("Workbench group contains World Forge and GM Assistant only", () => {
    renderSidebar();
    expect(screen.getByRole("link", { name: /World Forge/ })).toHaveAttribute("href", "/forge");
    expect(screen.getByRole("link", { name: /GM Assistant/ })).toHaveAttribute("href", "/gm");
    for (const gone of ["Play", "Characters", "Search", "Explorer", "History"]) {
      expect(screen.queryByRole("link", { name: gone })).not.toBeInTheDocument();
    }
  });

  it("Configuration group links /config", () => {
    renderSidebar();
    expect(screen.getByRole("link", { name: /Configuration/ })).toHaveAttribute("href", "/config");
  });

  it("no longer renders WorldPicker or ModeSwitcher in the footer", () => {
    renderSidebar();
    expect(screen.queryByTestId("world-picker")).not.toBeInTheDocument();
    expect(screen.queryByTestId("mode-switcher")).not.toBeInTheDocument();
    expect(screen.getByTestId("connection-status")).toBeInTheDocument();
  });

  it("highlights Campaigns only on exactly /", () => {
    renderSidebar("/light-rp");
    expect(screen.getByRole("link", { name: /Light RP/ })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: /Campaigns/ })).not.toHaveAttribute("aria-current");
  });

  it("highlights World Forge on nested forge routes", () => {
    renderSidebar("/forge/packs");
    expect(screen.getByRole("link", { name: /World Forge/ })).toHaveAttribute("aria-current", "page");
  });
});
