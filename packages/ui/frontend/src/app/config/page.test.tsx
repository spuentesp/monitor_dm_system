// @vitest-environment happy-dom
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, within, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import SettingsPage from "./page";
import * as api from "@/lib/api";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));

beforeEach(() => {
  vi.restoreAllMocks();
  globalThis.fetch = vi.fn(() =>
    Promise.resolve(new Response(JSON.stringify({}), { status: 200, headers: { "Content-Type": "application/json" } })),
  ) as unknown as typeof fetch;
  // The page mounts the LLM tab by default; give its queries sane data.
  vi.spyOn(api.llmApi, "listProviders").mockResolvedValue([]);
  vi.spyOn(api.llmApi, "listAssignments").mockResolvedValue([]);
  vi.spyOn(api.dbApi, "allStatus").mockResolvedValue([]);
});

// Helper: useEffect-tick-safe click that doesn't depend on userEvent setup().
// Hoisted above the describe blocks so the order in the file matches the
// order the helper is referenced; the previous bottom-of-file declaration
// worked thanks to function hoisting but read confusingly.
async function userClick(el: HTMLElement) {
  const user = userEvent.setup();
  await user.click(el);
}

describe("/settings — tone tab (F1-5a)", () => {
  it("links to /forge/style instead of rendering an inline ToneTab", async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const user = userEvent.setup();
    render(
      <QueryClientProvider client={qc}>
        <SettingsPage />
      </QueryClientProvider>,
    );

    await user.click(screen.getByRole("button", { name: /^tone$/i }));

    const link = await screen.findByRole("link", { name: /open forge/i });
    expect(link).toHaveAttribute("href", "/forge/style");
    // The inline tone CRUD UI is gone — no profile form on this page.
    expect(screen.queryByPlaceholderText(/profile name/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /add profile/i })).not.toBeInTheDocument();
  });
});

describe("/config — image role", () => {
  it("offers the image role in the add-provider role select", async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const user = userEvent.setup();
    render(
      <QueryClientProvider client={qc}>
        <SettingsPage />
      </QueryClientProvider>,
    );

    await user.click(await screen.findByRole("button", { name: /add provider/i }));
    const roleSelect = screen.getByRole("combobox", { name: /role tier/i });
    // Scope the option query to the select: in happy-dom the option node found via a
    // second global getByRole is not identity-equal to the select's child, which
    // breaks toContainElement across the two queries.
    expect(within(roleSelect).getByRole("option", { name: /image generation/i })).toBeInTheDocument();
  });
});

describe("/config — image generation tab (Task 10)", () => {
  const SETTINGS = {
    image_moderation_mode: "provider_default" as const,
    image_max_per_scene: 4,
    image_max_per_conversation: 8,
    image_max_per_actor_hour: 12,
    image_suggestions_enabled: true,
  };

  beforeEach(() => {
    vi.spyOn(api.imageApi, "getImageGenerationSettings").mockResolvedValue(SETTINGS);
    vi.spyOn(api.imageApi, "updateImageGenerationSettings").mockResolvedValue(SETTINGS);
  });

  it("renders the image tab with the current settings", async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const user = userEvent.setup();
    render(
      <QueryClientProvider client={qc}>
        <SettingsPage />
      </QueryClientProvider>,
    );

    await user.click(screen.getByRole("button", { name: /^image generation$/i }));

    // The mode select reflects the GET result.
    const modeSelect = await screen.findByRole("combobox", { name: /moderation mode/i });
    expect(within(modeSelect).getByRole("option", { name: /provider default/i })).toBeInTheDocument();
    expect(within(modeSelect).getByRole("option", { name: /lines and veils/i })).toBeInTheDocument();

    // The budget inputs are populated with the configured values. The numbers
    // arrive after the GET resolves, so we wait for the first one to match.
    const sceneInput = await screen.findByRole("spinbutton", { name: /per scene/i });
    await vi.waitFor(() => expect(sceneInput).toHaveValue(4));
    const conversationInput = screen.getByRole("spinbutton", { name: /per conversation/i });
    expect(conversationInput).toHaveValue(8);
    const actorHourInput = screen.getByRole("spinbutton", { name: /per actor per hour/i });
    expect(actorHourInput).toHaveValue(12);

    // And the toggle for suggestion chips is on.
    expect(screen.getByRole("checkbox", { name: /image suggestions/i })).toBeChecked();
  });

  it("shows the explanatory copy about provider safety rules", async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const user = userEvent.setup();
    render(
      <QueryClientProvider client={qc}>
        <SettingsPage />
      </QueryClientProvider>,
    );

    await user.click(screen.getByRole("button", { name: /^image generation$/i }));

    // The advisory text is rendered next to the controls.
    expect(await screen.findByText(/provider safety rules still apply/i)).toBeInTheDocument();
    expect(screen.getByText(/cannot override provider-level moderation/i)).toBeInTheDocument();
  });

  it("persists a new mode via PUT /image/settings", async () => {
    const updates: unknown[] = [];
    vi.spyOn(api.imageApi, "updateImageGenerationSettings").mockImplementation(async (changes) => {
      updates.push(changes);
      return { ...SETTINGS, ...changes };
    });

    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <SettingsPage />
      </QueryClientProvider>,
    );

    await userClick(screen.getByRole("button", { name: /^image generation$/i }));

    const modeSelect = await screen.findByRole("combobox", { name: /moderation mode/i });
    fireEvent.change(modeSelect, { target: { value: "lines_and_veils" } });

    await vi.waitFor(() => expect(updates.length).toBeGreaterThan(0));
    const last = updates[updates.length - 1] as Record<string, unknown>;
    expect(last.image_moderation_mode).toBe("lines_and_veils");
  });

  it("persists a new per-scene budget via PUT /image/settings", async () => {
    const updates: unknown[] = [];
    vi.spyOn(api.imageApi, "updateImageGenerationSettings").mockImplementation(async (changes) => {
      updates.push(changes);
      return { ...SETTINGS, ...changes };
    });

    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <SettingsPage />
      </QueryClientProvider>,
    );

    await userClick(screen.getByRole("button", { name: /^image generation$/i }));

    const sceneInput = await screen.findByRole("spinbutton", { name: /per scene/i });
    fireEvent.change(sceneInput, { target: { value: "7" } });

    await vi.waitFor(() => expect(updates.length).toBeGreaterThan(0));
    const last = updates[updates.length - 1] as Record<string, unknown>;
    expect(last.image_max_per_scene).toBe(7);
  });

  it("toggles image_suggestions_enabled via PUT /image/settings", async () => {
    const updates: unknown[] = [];
    vi.spyOn(api.imageApi, "updateImageGenerationSettings").mockImplementation(async (changes) => {
      updates.push(changes);
      return { ...SETTINGS, ...changes };
    });

    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const user = userEvent.setup();
    render(
      <QueryClientProvider client={qc}>
        <SettingsPage />
      </QueryClientProvider>,
    );

    await user.click(screen.getByRole("button", { name: /^image generation$/i }));

    const checkbox = await screen.findByRole("checkbox", { name: /image suggestions/i });
    await user.click(checkbox);

    await vi.waitFor(() => expect(updates.length).toBeGreaterThan(0));
    const last = updates[updates.length - 1] as Record<string, unknown>;
    expect(last.image_suggestions_enabled).toBe(false);
  });
});
