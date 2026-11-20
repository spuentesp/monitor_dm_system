// @vitest-environment happy-dom
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const mockPush = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush, replace: vi.fn() }),
  usePathname: () => "/settings/account",
}));

type MockMe = {
  auth_disabled: boolean;
  user: {
    id: string;
    email: string;
    username: string;
    display_name: string;
    is_admin: boolean;
    created_at: string;
    updated_at: string;
  };
};

let mockMe: MockMe;
const mockChangePassword = vi.fn();
const mockListSessions = vi.fn();
const mockRevokeSession = vi.fn();
const mockRevokeAllSessions = vi.fn();
const mockListTokens = vi.fn();
const mockCreateToken = vi.fn();
const mockRevokeToken = vi.fn();

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    authApi: {
      me: () => Promise.resolve(mockMe),
      changePassword: (current: string, next: string) => mockChangePassword(current, next),
      listSessions: () => mockListSessions(),
      revokeSession: (prefix: string) => mockRevokeSession(prefix),
      revokeAllSessions: () => mockRevokeAllSessions(),
      listTokens: () => mockListTokens(),
      createToken: (name: string, expires_at?: string | null) => mockCreateToken(name, expires_at),
      revokeToken: (id: string) => mockRevokeToken(id),
    },
  };
});

import AccountPage from "./page";
import { NotificationProvider } from "@/components/NotificationProvider";
import { ApiError } from "@/lib/api";

const SESSIONS = {
  sessions: [
    {
      token_hash_prefix: "aaaa11112222",
      created_at: "2026-11-01T10:00:00Z",
      expires_at: "2026-12-01T10:00:00Z",
      last_seen_at: "2026-11-19T10:00:00Z",
      current: true,
    },
    {
      token_hash_prefix: "bbbb33334444",
      created_at: "2026-11-10T10:00:00Z",
      expires_at: "2026-12-10T10:00:00Z",
      last_seen_at: null,
      current: false,
    },
  ],
};

const TOKENS = [
  {
    id: "tok-1",
    name: "CLI laptop",
    token_prefix: "mon_ab12",
    created_at: "2026-11-01T10:00:00Z",
    expires_at: null,
    last_used_at: null,
    revoked_at: null,
  },
  {
    id: "tok-2",
    name: "Old script",
    token_prefix: "mon_cd34",
    created_at: "2026-10-01T10:00:00Z",
    expires_at: null,
    last_used_at: null,
    revoked_at: "2026-10-15T10:00:00Z",
  },
];

function renderAccount() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <NotificationProvider>
        <AccountPage />
      </NotificationProvider>
    </QueryClientProvider>,
  );
}

function section(title: string): HTMLElement {
  const heading = screen.getByRole("heading", { name: title });
  const el = heading.closest("section");
  if (!el) throw new Error(`no section for ${title}`);
  return el as HTMLElement;
}

beforeEach(() => {
  vi.clearAllMocks();
  mockPush.mockReset();
  mockMe = {
    auth_disabled: false,
    user: {
      id: "u1",
      email: "ada@example.com",
      username: "ada",
      display_name: "Ada Lovelace",
      is_admin: false,
      created_at: "2026-01-15T00:00:00Z",
      updated_at: "2026-01-15T00:00:00Z",
    },
  };
  mockChangePassword.mockResolvedValue({ ok: true, other_sessions_revoked: 1 });
  mockListSessions.mockResolvedValue(SESSIONS);
  mockRevokeSession.mockResolvedValue(undefined);
  mockRevokeAllSessions.mockResolvedValue(undefined);
  mockListTokens.mockResolvedValue(TOKENS);
  mockCreateToken.mockResolvedValue({
    id: "tok-new",
    name: "fresh",
    token: "sk-raw-once-token",
    token_prefix: "sk_ra",
    created_at: "2026-11-20T00:00:00Z",
    expires_at: null,
  });
  mockRevokeToken.mockResolvedValue(undefined);
});

describe("/settings/account profile", () => {
  it("shows profile details", async () => {
    renderAccount();
    expect(await screen.findByRole("heading", { name: "Account" })).toBeInTheDocument();
    expect(screen.getByText("Ada Lovelace")).toBeInTheDocument();
    expect(screen.getByText("ada@example.com")).toBeInTheDocument();
    expect(screen.getByText("ada")).toBeInTheDocument();
    expect(screen.getByText("user")).toBeInTheDocument();
  });

  it("hides password/sessions/tokens in auth-disabled local mode", async () => {
    mockMe.auth_disabled = true;
    renderAccount();
    expect(await screen.findByRole("heading", { name: "Profile" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Change password" })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Active sessions" })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "API tokens" })).not.toBeInTheDocument();
  });
});

describe("/settings/account change password", () => {
  it("rejects mismatched confirmation client-side", async () => {
    const user = userEvent.setup();
    renderAccount();
    await screen.findByRole("heading", { name: "Change password" });

    await user.type(screen.getByLabelText("Current password"), "old-password-1");
    await user.type(screen.getByLabelText("New password"), "brand-new-pass-1");
    await user.type(screen.getByLabelText("Confirm new password"), "different-pass-1");
    await user.click(screen.getByRole("button", { name: /update password/i }));

    expect(await screen.findByText("New passwords do not match.")).toBeInTheDocument();
    expect(mockChangePassword).not.toHaveBeenCalled();
  });

  it("changes the password and reports success", async () => {
    const user = userEvent.setup();
    renderAccount();
    await screen.findByRole("heading", { name: "Change password" });

    await user.type(screen.getByLabelText("Current password"), "old-password-1");
    await user.type(screen.getByLabelText("New password"), "brand-new-pass-1");
    await user.type(screen.getByLabelText("Confirm new password"), "brand-new-pass-1");
    await user.click(screen.getByRole("button", { name: /update password/i }));

    await waitFor(() =>
      expect(mockChangePassword).toHaveBeenCalledWith("old-password-1", "brand-new-pass-1"),
    );
    expect(await screen.findByText(/password updated/i)).toBeInTheDocument();
  });

  it("shows a wrong current password distinctly (401)", async () => {
    const user = userEvent.setup();
    mockChangePassword.mockRejectedValue(new ApiError(401, '{"detail":"Invalid current password."}'));
    renderAccount();
    await screen.findByRole("heading", { name: "Change password" });

    await user.type(screen.getByLabelText("Current password"), "wrong-password");
    await user.type(screen.getByLabelText("New password"), "brand-new-pass-1");
    await user.type(screen.getByLabelText("Confirm new password"), "brand-new-pass-1");
    await user.click(screen.getByRole("button", { name: /update password/i }));

    expect(await screen.findByText("Current password is incorrect.")).toBeInTheDocument();
  });
});

describe("/settings/account sessions", () => {
  it("lists sessions and marks the current one", async () => {
    renderAccount();
    const card = await screen
      .findByRole("heading", { name: "Active sessions" })
      .then((h) => h.closest("section") as HTMLElement);
    expect(await within(card).findByText("aaaa11112222…")).toBeInTheDocument();
    expect(within(card).getByText("bbbb33334444…")).toBeInTheDocument();
    expect(within(card).getAllByText("current")).toHaveLength(1);
  });

  it("revokes a single session after confirmation", async () => {
    const user = userEvent.setup();
    renderAccount();
    const card = await screen
      .findByRole("heading", { name: "Active sessions" })
      .then((h) => h.closest("section") as HTMLElement);

    await user.click(await within(card).findByRole("button", { name: "Revoke" }));
    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent(/revoke this session/i);
    await user.click(within(dialog).getByRole("button", { name: "Revoke" }));

    await waitFor(() => expect(mockRevokeSession).toHaveBeenCalledWith("bbbb33334444"));
    await waitFor(() => expect(mockRevokeSession).not.toHaveBeenCalledWith("aaaa11112222"));
  });

  it("signs out everywhere via DELETE /sessions and redirects to login", async () => {
    const user = userEvent.setup();
    renderAccount();
    const card = await screen
      .findByRole("heading", { name: "Active sessions" })
      .then((h) => h.closest("section") as HTMLElement);

    await user.click(await within(card).findByRole("button", { name: /sign out everywhere/i }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: /sign out everywhere/i }));

    await waitFor(() => expect(mockRevokeAllSessions).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(mockPush).toHaveBeenCalledWith("/login"));
  });
});

describe("/settings/account API tokens", () => {
  it("lists tokens with revoked state", async () => {
    renderAccount();
    const card = await screen
      .findByRole("heading", { name: "API tokens" })
      .then((h) => h.closest("section") as HTMLElement);
    expect(await within(card).findByText("CLI laptop")).toBeInTheDocument();
    expect(within(card).getByText("Old script")).toBeInTheDocument();
    expect(within(card).getAllByText("revoked")).toHaveLength(1);
    // Revoked rows have no revoke button.
    expect(within(card).getAllByRole("button", { name: /revoke/i })).toHaveLength(1);
  });

  it("creates a token and shows the raw value exactly once in a copy dialog", async () => {
    const user = userEvent.setup();
    renderAccount();
    const card = await screen
      .findByRole("heading", { name: "API tokens" })
      .then((h) => h.closest("section") as HTMLElement);

    await user.type(within(card).getByLabelText("Name"), "fresh token");
    await user.click(within(card).getByRole("button", { name: /create token/i }));

    await waitFor(() => expect(mockCreateToken).toHaveBeenCalledWith("fresh token", null));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByDisplayValue("sk-raw-once-token")).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: /copy/i })).toBeInTheDocument();
  });

  it("revokes a token", async () => {
    const user = userEvent.setup();
    renderAccount();
    const card = await screen
      .findByRole("heading", { name: "API tokens" })
      .then((h) => h.closest("section") as HTMLElement);

    const revokeBtn = await within(card).findByRole("button", { name: /revoke/i });
    await user.click(revokeBtn);
    await waitFor(() => expect(mockRevokeToken).toHaveBeenCalledWith("tok-1"));
  });
});
