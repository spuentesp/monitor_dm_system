// @vitest-environment happy-dom
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { PerformanceTab } from "./PerformanceTab";
import * as api from "@/lib/api";

const emptyOverview = {
  request_count: 0,
  avg_latency_ms: 0,
  p95_ms: 0,
  slow_query_count: 0,
  recent_alerts: [],
};

beforeEach(() => {
  globalThis.fetch = vi.fn(() =>
    Promise.resolve(new Response("{}", { status: 200, headers: { "Content-Type": "application/json" } })),
  ) as unknown as typeof fetch;
});

function renderPerf() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <PerformanceTab />
    </QueryClientProvider>,
  );
}

describe("PerformanceTab", () => {
  it("renders the section header without crashing", async () => {
    vi.spyOn(api.performanceApi, "overview").mockResolvedValue(emptyOverview as unknown as Awaited<ReturnType<typeof api.performanceApi.overview>>);
    vi.spyOn(api.performanceApi, "slowQueries").mockResolvedValue([] as unknown as Awaited<ReturnType<typeof api.performanceApi.slowQueries>>);
    vi.spyOn(api.performanceApi, "alerts").mockResolvedValue([] as unknown as Awaited<ReturnType<typeof api.performanceApi.alerts>>);
    renderPerf();
    await waitFor(() => expect(screen.getByText("Performance")).toBeInTheDocument());
    expect(screen.getByText("Performance")).toBeInTheDocument();
  });

  it("renders the four metric cards", async () => {
    vi.spyOn(api.performanceApi, "overview").mockResolvedValue(emptyOverview as unknown as Awaited<ReturnType<typeof api.performanceApi.overview>>);
    vi.spyOn(api.performanceApi, "slowQueries").mockResolvedValue([] as unknown as Awaited<ReturnType<typeof api.performanceApi.slowQueries>>);
    vi.spyOn(api.performanceApi, "alerts").mockResolvedValue([] as unknown as Awaited<ReturnType<typeof api.performanceApi.alerts>>);
    renderPerf();
    await waitFor(() => expect(screen.getByText("Requests")).toBeInTheDocument());
    expect(screen.getByText("Requests")).toBeInTheDocument();
    expect(screen.getByText("Avg latency")).toBeInTheDocument();
    expect(screen.getByText("p95")).toBeInTheDocument();
    expect(screen.getAllByText("Slow queries").length).toBeGreaterThan(0);
  });

  it("shows empty state when no slow queries", async () => {
    vi.spyOn(api.performanceApi, "overview").mockResolvedValue(emptyOverview as unknown as Awaited<ReturnType<typeof api.performanceApi.overview>>);
    vi.spyOn(api.performanceApi, "slowQueries").mockResolvedValue([] as unknown as Awaited<ReturnType<typeof api.performanceApi.slowQueries>>);
    vi.spyOn(api.performanceApi, "alerts").mockResolvedValue([] as unknown as Awaited<ReturnType<typeof api.performanceApi.alerts>>);
    renderPerf();
    await waitFor(() => expect(screen.getByText("None recorded.")).toBeInTheDocument());
  });
});
