// @vitest-environment happy-dom
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => "/admin",
}));

type MockMe = {
  auth_disabled: boolean;
  user: { id: string; email: string; username: string; display_name: string; is_admin: boolean; created_at: string; updated_at: string };
};

let mockMe: MockMe;
const mockListUsers = vi.fn();
const mockBan = vi.fn();
const mockResetUserPassword = vi.fn();
const mockRevokeUserSessions = vi.fn();
const mockListInvites = vi.fn();
const mockCreateInvite = vi.fn();
const mockRevokeInvite = vi.fn();
const mockUsage = vi.fn();
const mockSetUsageLimits = vi.fn();

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    authApi: {
      me: () => Promise.resolve(mockMe),
    },
    adminApi: {
      listUsers: (q?: string) => mockListUsers(q),
      ban: (id: string, reason?: string) => mockBan(id, reason),
      resetUserPassword: (id: string) => mockResetUserPassword(id),
      revokeUserSessions: (id: string) => mockRevokeUserSessions(id),
      listInvites: () => mockListInvites(),
      createInvite: (email?: string, hours?: number) => mockCreateInvite(email, hours),
      revokeInvite: (id: string) => mockRevokeInvite(id),
      usage: () => mockUsage(),
      setUsageLimits: (id: string, limits: unknown) => mockSetUsageLimits(id, limits),
    },
    llmApi: {
      ...actual.llmApi,
      listProviders: () => Promise.resolve([]),
      listModels: () => Promise.resolve([]),
    },
  };
});

import AdminPage from "./page";
import { NotificationProvider } from "@/components/NotificationProvider";

const ADMIN_ME: MockMe = {
  auth_disabled: false,
  user: { id: "admin-1", email: "boss@x.com", username: "boss", display_name: "Boss", is_admin: true, created_at: "", updated_at: "" },
};

const USER_ROW = {
  id: "u2",
  email: "ada@example.com",
  username: "ada",
  display_name: "Ada",
  is_admin: false,
  is_banned: false,
  banned_reason: null,
  email_verified: true,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

function renderAdmin() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <NotificationProvider>
        <AdminPage />
      </NotificationProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mockMe = ADMIN_ME;
  mockListUsers.mockResolvedValue({ users: [USER_ROW], total: 1, limit: 50, offset: 0 });
  mockBan.mockResolvedValue(USER_ROW);
  mockResetUserPassword.mockResolvedValue({
    token: "rst_abc",
    url_path: "/reset-password?token=rst_abc",
    expires_at: "2026-11-20T12:00:00Z",
  });
  mockRevokeUserSessions.mockResolvedValue(undefined);
  mockListInvites.mockResolvedValue({
    invites: [
      {
        id: "inv-1",
        email: "friend@example.com",
        created_at: "2026-11-01T00:00:00Z",
        expires_at: "2099-01-01T00:00:00Z",
        used_at: null,
        revoked_at: null,
        created_by: "admin-1",
      },
    ],
  });
  mockCreateInvite.mockResolvedValue({
    id: "inv-2",
    token: "tok1",
    url_path: "/login?invite=tok1",
    expires_at: "2099-01-01T00:00:00Z",
  });
  mockRevokeInvite.mockResolvedValue(undefined);
  mockUsage.mockResolvedValue({
    day: "2026-11-20",
    users: [
      {
        user_id: "u2",
        username: "ada",
        email: "ada@example.com",
        tokens: 12000,
        calls: 90,
        daily_token_cap: 10000,
        daily_call_cap: null,
        exempt: false,
      },
      {
        user_id: "u3",
        username: "bob",
        email: "bob@example.com",
        tokens: 100,
        calls: 5,
        daily_token_cap: 10000,
        daily_call_cap: 100,
        exempt: false,
      },
    ],
  });
  mockSetUsageLimits.mockResolvedValue({});
});

describe("/admin access", () => {
  it("shows operator-access-required for non-admins", async () => {
    mockMe = {
      auth_disabled: false,
      user: { id: "u2", email: "ada@example.com", username: "ada", display_name: "Ada", is_admin: false, created_at: "", updated_at: "" },
    };
    renderAdmin();
    expect(await screen.findByText("Operator access required.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /invites/i })).not.toBeInTheDocument();
    expect(mockListUsers).not.toHaveBeenCalled();
  });

  it("renders the four tabs for admins with Users active", async () => {
    renderAdmin();
    expect(await screen.findByRole("heading", { name: "Users" })).toBeInTheDocument();
    for (const name of ["Users", "Invites", "Usage", "Providers"]) {
      expect(screen.getByRole("button", { name })).toBeInTheDocument();
    }
    expect(await screen.findByText("ada")).toBeInTheDocument();
  });
});

describe("/admin Users tab", () => {
  it("bans through a confirmation dialog that carries the reason", async () => {
    const user = userEvent.setup();
    renderAdmin();
    await screen.findByText("ada");

    await user.click(screen.getByRole("button", { name: "Ban" }));
    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent(/blocked from signing in/i);

    await user.type(within(dialog).getByLabelText(/ban reason/i), "spamming other players");
    await user.click(within(dialog).getByRole("button", { name: "Ban account" }));

    await waitFor(() => expect(mockBan).toHaveBeenCalledWith("u2", "spamming other players"));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("issues a password-reset link shown once in a copy dialog", async () => {
    const user = userEvent.setup();
    renderAdmin();
    await screen.findByText("ada");

    await user.click(screen.getByRole("button", { name: /reset password/i }));

    await waitFor(() => expect(mockResetUserPassword).toHaveBeenCalledWith("u2"));
    const dialog = await screen.findByRole("dialog");
    const expected = `${window.location.origin}/reset-password?token=rst_abc`;
    expect(within(dialog).getByDisplayValue(expected)).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: /copy/i })).toBeInTheDocument();
  });

  it("revokes all sessions of a user after confirmation", async () => {
    const user = userEvent.setup();
    renderAdmin();
    await screen.findByText("ada");

    await user.click(screen.getByRole("button", { name: /revoke sessions/i }));
    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent(/sign ada out of every device/i);
    await user.click(within(dialog).getByRole("button", { name: /revoke all sessions/i }));

    await waitFor(() => expect(mockRevokeUserSessions).toHaveBeenCalledWith("u2"));
  });
});

describe("/admin Invites tab", () => {
  it("creates an invite and shows the absolute link once", async () => {
    const user = userEvent.setup();
    renderAdmin();
    await user.click(await screen.findByRole("button", { name: "Invites" }));

    await user.type(await screen.findByLabelText(/restrict to email/i), "friend@example.com");
    await user.click(screen.getByRole("button", { name: /create invite/i }));

    await waitFor(() => expect(mockCreateInvite).toHaveBeenCalledWith("friend@example.com", 168));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByDisplayValue(`${window.location.origin}/login?invite=tok1`)).toBeInTheDocument();
  });

  it("lists invites with status and revokes them", async () => {
    const user = userEvent.setup();
    renderAdmin();
    await user.click(await screen.findByRole("button", { name: "Invites" }));

    expect(await screen.findByText("friend@example.com")).toBeInTheDocument();
    expect(screen.getByText("active")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Revoke" }));
    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent(/stop working immediately/i);
    await user.click(within(dialog).getByRole("button", { name: /revoke invite/i }));

    await waitFor(() => expect(mockRevokeInvite).toHaveBeenCalledWith("inv-1"));
  });
});

describe("/admin Usage tab", () => {
  it("shows daily usage vs caps with an over-cap badge", async () => {
    const user = userEvent.setup();
    renderAdmin();
    await user.click(await screen.findByRole("button", { name: "Usage" }));

    expect(await screen.findByText("over cap")).toBeInTheDocument();
    expect(screen.getByText(/1 user\(s\) over cap/i)).toBeInTheDocument();
    expect(screen.getByText(/12[.,]?000/)).toBeInTheDocument();
    expect(screen.getByText("within limits")).toBeInTheDocument();
  });

  it("saves edited caps and the exempt flag inline", async () => {
    const user = userEvent.setup();
    renderAdmin();
    await user.click(await screen.findByRole("button", { name: "Usage" }));

    const tokenCap = await screen.findByLabelText("Daily token cap for ada");
    await user.clear(tokenCap);
    await user.type(tokenCap, "20000");
    const adaRow = tokenCap.closest("tr") as HTMLElement;
    await user.click(within(adaRow).getByRole("checkbox"));
    await user.click(screen.getByRole("button", { name: "Save limits for ada" }));

    await waitFor(() =>
      expect(mockSetUsageLimits).toHaveBeenCalledWith("u2", {
        daily_token_cap: 20000,
        daily_call_cap: null,
        exempt: true,
      }),
    );
  });
});

describe("/admin Providers tab", () => {
  it("renders the shared LLM provider management panel", async () => {
    const user = userEvent.setup();
    renderAdmin();
    await user.click(await screen.findByRole("button", { name: "Providers" }));

    expect(await screen.findByRole("heading", { name: /llm providers/i })).toBeInTheDocument();
    expect(await screen.findByText(/no llm providers configured yet/i)).toBeInTheDocument();
  });
});
