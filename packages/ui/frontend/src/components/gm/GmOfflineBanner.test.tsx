// @vitest-environment happy-dom
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { systemApi } from "@/lib/api";
import { GmOfflineBanner } from "./GmOfflineBanner";

function renderBanner() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <GmOfflineBanner />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.restoreAllMocks();
});

describe("GmOfflineBanner", () => {
  it("stays hidden while the backend is healthy", async () => {
    vi.spyOn(systemApi, "getHealth").mockResolvedValue({
      status: "ok",
      components: {},
    } as never);
    renderBanner();
    await waitFor(() => expect(vi.mocked(systemApi.getHealth)).toHaveBeenCalled());
    expect(screen.queryByTestId("gm-offline-banner")).not.toBeInTheDocument();
  });

  it("explains that dice and notes still work when the backend is unreachable", async () => {
    vi.spyOn(systemApi, "getHealth").mockRejectedValue(new Error("ECONNREFUSED"));
    renderBanner();

    const banner = await screen.findByTestId("gm-offline-banner");
    expect(banner).toHaveTextContent(/backend unreachable/i);
    expect(banner).toHaveTextContent(/dice and notes still work/i);
    // No raw exception text leaks into the table UI.
    expect(banner).not.toHaveTextContent("ECONNREFUSED");
  });

  it("shows the degraded variant when health reports a non-ok status", async () => {
    vi.spyOn(systemApi, "getHealth").mockResolvedValue({
      status: "degraded",
      components: { neo4j: "offline" },
    } as never);
    renderBanner();

    const banner = await screen.findByTestId("gm-offline-banner");
    expect(banner).toHaveTextContent(/backend degraded/i);
    expect(banner).toHaveTextContent(/dice and notes still work/i);
  });
});
