// @vitest-environment happy-dom
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// Mock next/navigation so we can drive useSearchParams per test.
let mockSearchParams: URLSearchParams = new URLSearchParams();
vi.mock("next/navigation", () => ({
  useSearchParams: () => mockSearchParams,
}));

import { WorldPicker } from "./WorldPicker";
import { useWorldContext } from "@/lib/world-context";

vi.mock("@/lib/world-context", () => ({
  useWorldContext: vi.fn(() => ({
    universeId: null,
    multiverseId: null,
    universeLabel: null,
    setWorld: vi.fn(),
    clearWorld: vi.fn(),
  })),
}));

// Stub the api module so the queries don't try to fetch.
vi.mock("@/lib/api", () => ({
  universesApi: {
    listMultiverses: vi.fn(async () => []),
    listUniverses: vi.fn(async () => []),
  },
}));

beforeEach(() => {
  mockSearchParams = new URLSearchParams();
  vi.mocked(useWorldContext).mockReturnValue({
    universeId: null,
    multiverseId: null,
    universeLabel: null,
    setWorld: vi.fn(),
    clearWorld: vi.fn(),
  });
});

function renderWorld() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return render(<WorldPicker collapsed={false} />, { wrapper });
}

describe("WorldPicker drift indicator", () => {
  it("shows no drift badge when not on a session route", () => {
    mockSearchParams = new URLSearchParams();
    vi.mocked(useWorldContext).mockReturnValue({
      universeId: null,
      multiverseId: null,
      universeLabel: null,
      setWorld: vi.fn(),
      clearWorld: vi.fn(),
    });
    renderWorld();
    expect(screen.queryByText(/session/)).not.toBeInTheDocument();
  });

  it("shows no drift badge when session universe matches persisted", () => {
    const u = "u-1";
    mockSearchParams = new URLSearchParams(`universe=${u}`);
    vi.mocked(useWorldContext).mockReturnValue({
      universeId: u,
      multiverseId: null,
      universeLabel: "Test",
      setWorld: vi.fn(),
      clearWorld: vi.fn(),
    });
    renderWorld();
    expect(screen.queryByText(/session/)).not.toBeInTheDocument();
  });

  it("shows a drift badge when session universe differs from persisted", () => {
    mockSearchParams = new URLSearchParams("universe=u-session");
    vi.mocked(useWorldContext).mockReturnValue({
      universeId: "u-persisted",
      multiverseId: null,
      universeLabel: "Persisted",
      setWorld: vi.fn(),
      clearWorld: vi.fn(),
    });
    renderWorld();
    expect(screen.getByText(/session/)).toBeInTheDocument();
  });
});
