// @vitest-environment happy-dom
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";

// Mock next/navigation so we can drive usePathname per test.
let mockPathname = "/forge";
vi.mock("next/navigation", () => ({
  usePathname: () => mockPathname,
}));

import ForgeLayout from "./layout";
import { FORGE_SECTIONS, isForgeSectionActive } from "@/lib/forge-sections";

function renderLayout(pathname = "/forge") {
  mockPathname = pathname;
  return render(
    <ForgeLayout>
      <div>content</div>
    </ForgeLayout>,
  );
}

describe("Forge layout section nav (F1-1)", () => {
  it("defines the 12 target-IA sections", () => {
    expect(FORGE_SECTIONS).toHaveLength(12);
    expect(FORGE_SECTIONS.map((s) => s.href)).toEqual([
      "/forge",
      "/forge/worlds",
      "/forge/ontology",
      "/forge/architect",
      "/forge/ingest",
      "/forge/packs",
      "/forge/review",
      "/forge/systems",
      "/forge/style",
      "/forge/templates",
      "/forge/prompts",
      "/forge/snapshots",
    ]);
  });

  it("renders a nav link for each of the 12 sections", () => {
    renderLayout();
    for (const label of [
      "Overview",
      "Worlds",
      "Ontology",
      "Architect",
      "Ingest Studio",
      "Packs",
      "Canon Review",
      "Systems",
      "Style",
      "Templates",
      "Prompts",
      "Snapshots",
    ]) {
      expect(screen.getByRole("link", { name: label })).toBeInTheDocument();
    }
  });

  it("marks only Overview active on /forge exactly", () => {
    renderLayout("/forge");
    expect(screen.getByRole("link", { name: "Overview" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Packs" })).not.toHaveAttribute("aria-current");
  });

  it("marks Packs active on the nested apply/editor routes", () => {
    renderLayout("/forge/apply");
    expect(screen.getByRole("link", { name: "Packs" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Overview" })).not.toHaveAttribute("aria-current");
  });

  it("isForgeSectionActive matches nested section routes", () => {
    const worlds = FORGE_SECTIONS.find((s) => s.href === "/forge/worlds")!;
    expect(isForgeSectionActive(worlds, "/forge/worlds")).toBe(true);
    expect(isForgeSectionActive(worlds, "/forge/worlds/new")).toBe(true);
    expect(isForgeSectionActive(worlds, "/forge/packs")).toBe(false);
  });
});
