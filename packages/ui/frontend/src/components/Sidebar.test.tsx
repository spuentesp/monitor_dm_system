// @vitest-environment happy-dom
import { describe, it, expect, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// Mock next/navigation so we can drive usePathname per test.
let mockPathname = "/";
vi.mock("next/navigation", () => ({
  usePathname: () => mockPathname,
  useRouter: () => ({ push: vi.fn() }),
}));

// Auth query: default to a non-admin local-mode user; tests can override.
let mockMe: unknown = { auth_disabled: true, user: { id: "u", email: "e", username: "local", display_name: "", is_admin: false, created_at: "", updated_at: "" } };
const mockLogout = vi.fn(() => Promise.resolve({ ok: true }));
vi.mock("@/lib/api", () => ({
  authApi: {
    me: () => Promise.resolve(mockMe),
    logout: () => mockLogout(),
  },
}));

vi.mock("@/components/ConnectionStatus", () => ({
  ConnectionStatus: () => <div data-testid="connection-status" />,
}));

import { Sidebar } from "./Sidebar";

function renderSidebar(pathname = "/") {
  mockPathname = pathname;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <Sidebar />
    </QueryClientProvider>,
  );
}

const ADMIN_ME = { auth_disabled: false, user: { id: "u", email: "boss@example.com", username: "boss", display_name: "The Boss", is_admin: true, created_at: "", updated_at: "" } };
const USER_ME = { auth_disabled: false, user: { id: "u", email: "bob@example.com", username: "bob", display_name: "Bob", is_admin: false, created_at: "", updated_at: "" } };

describe("Sidebar two-tier nav", () => {
  it("renders Lobby and Workbench for non-admins and hides the Configuration tier", () => {
    renderSidebar();
    expect(screen.getByText("Lobby")).toBeInTheDocument();
    expect(screen.getByText("Workbench")).toBeInTheDocument();
    // Configuration is operator-only: neither the tier label nor its item.
    expect(screen.queryByText("Configuration")).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Configuration/ })).not.toBeInTheDocument();
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

describe("Sidebar operator links", () => {
  it("shows Configuration and Admin nav items only for admins", async () => {
    mockMe = ADMIN_ME;
    const adminView = renderSidebar();
    expect(await screen.findByRole("link", { name: /Configuration/ })).toHaveAttribute("href", "/config");
    expect(screen.getByRole("link", { name: /^Admin/ })).toHaveAttribute("href", "/admin");
    adminView.unmount();

    mockMe = USER_ME;
    renderSidebar();
    await new Promise((r) => setTimeout(r, 50));
    expect(screen.queryByRole("link", { name: /Configuration/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /^Admin/ })).not.toBeInTheDocument();
    expect(screen.queryByText("Configuration")).not.toBeInTheDocument();
  });
});

describe("Sidebar user menu", () => {
  it("shows display name with Account link and Sign out", async () => {
    const user = userEvent.setup();
    mockMe = USER_ME;
    renderSidebar();

    const trigger = await screen.findByRole("button", { name: /account menu/i });
    expect(trigger).toHaveTextContent("Bob");
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();

    await user.click(trigger);
    const menu = await screen.findByRole("menu");
    expect(within(menu).getByText("Bob")).toBeInTheDocument();
    expect(within(menu).getByText("bob@example.com")).toBeInTheDocument();
    expect(within(menu).getByRole("menuitem", { name: /account/i })).toHaveAttribute(
      "href",
      "/settings/account",
    );

    mockLogout.mockClear();
    await user.click(within(menu).getByRole("menuitem", { name: /sign out/i }));
    expect(mockLogout).toHaveBeenCalledTimes(1);
  });

  it("keeps the Account link but hides Sign out in auth-disabled local mode", async () => {
    const user = userEvent.setup();
    mockMe = { auth_disabled: true, user: { id: "u", email: "local", username: "local", display_name: "", is_admin: true, created_at: "", updated_at: "" } };
    renderSidebar();

    await user.click(await screen.findByRole("button", { name: /account menu/i }));
    const menu = await screen.findByRole("menu");
    expect(within(menu).getByRole("menuitem", { name: /account/i })).toHaveAttribute(
      "href",
      "/settings/account",
    );
    expect(within(menu).queryByRole("menuitem", { name: /sign out/i })).not.toBeInTheDocument();
  });

  it("closes the menu on outside click", async () => {
    const user = userEvent.setup();
    mockMe = USER_ME;
    renderSidebar();

    await user.click(await screen.findByRole("button", { name: /account menu/i }));
    expect(await screen.findByRole("menu")).toBeInTheDocument();
    await user.click(document.body);
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  });
});
