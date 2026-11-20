// @vitest-environment happy-dom
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

let mockSearch = new URLSearchParams();
const mockPush = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush, replace: vi.fn() }),
  usePathname: () => "/login",
  useSearchParams: () => mockSearch,
}));

type MockConfig = {
  auth_disabled: boolean;
  google_oauth: boolean;
  signup_open: boolean;
  signup_invite_only: boolean;
  email_reset: boolean;
};

let mockConfig: MockConfig;
const mockLogin = vi.fn();
const mockSignup = vi.fn();

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    authApi: {
      config: () => Promise.resolve(mockConfig),
      login: (login: string, password: string) => mockLogin(login, password),
      signup: (email: string, username: string, password: string, display_name: string, invite_token?: string) =>
        mockSignup(email, username, password, display_name, invite_token),
      googleLoginUrl: () => "/api/auth/oauth/google",
    },
  };
});

import LoginPage from "./page";
import { ApiError } from "@/lib/api";

function renderLogin() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <LoginPage />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mockSearch = new URLSearchParams();
  mockConfig = {
    auth_disabled: false,
    google_oauth: false,
    signup_open: false,
    signup_invite_only: false,
    email_reset: true,
  };
  mockLogin.mockResolvedValue({ id: "u1" });
  mockSignup.mockResolvedValue({ id: "u1" });
});

describe("login ?next= return-to", () => {
  it("redirects to a validated same-origin path after sign-in", async () => {
    const user = userEvent.setup();
    mockSearch = new URLSearchParams("next=/forge/packs");
    renderLogin();

    await user.type(await screen.findByPlaceholderText("Email or username"), "ada");
    await user.type(screen.getByPlaceholderText(/password/i), "s3cret-pass");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => expect(mockPush).toHaveBeenCalledWith("/forge/packs"));
  });

  it("falls back to / for off-site or protocol-relative next values", async () => {
    const user = userEvent.setup();
    mockSearch = new URLSearchParams({ next: "https://evil.example/steal" });
    const first = renderLogin();

    await user.type(await screen.findByPlaceholderText("Email or username"), "ada");
    await user.type(screen.getByPlaceholderText(/password/i), "s3cret-pass");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => expect(mockPush).toHaveBeenCalledWith("/"));
    first.unmount();

    mockPush.mockClear();
    mockSearch = new URLSearchParams({ next: "//evil.example" });
    renderLogin();
    await user.type(await screen.findByPlaceholderText("Email or username"), "ada");
    await user.type(screen.getByPlaceholderText(/password/i), "s3cret-pass");
    await user.click(screen.getByRole("button", { name: /sign in/i }));
    await waitFor(() => expect(mockPush).toHaveBeenCalledWith("/"));
  });
});

describe("login password + links", () => {
  it("toggles password visibility", async () => {
    const user = userEvent.setup();
    renderLogin();
    const input = await screen.findByPlaceholderText("Password");
    expect(input).toHaveAttribute("type", "password");
    await user.click(screen.getByRole("button", { name: /show password/i }));
    expect(input).toHaveAttribute("type", "text");
    await user.click(screen.getByRole("button", { name: /hide password/i }));
    expect(input).toHaveAttribute("type", "password");
  });

  it("links to the forgot-password page", async () => {
    renderLogin();
    expect(await screen.findByRole("link", { name: /forgot password/i })).toHaveAttribute(
      "href",
      "/forgot-password",
    );
  });
});

describe("login error messages", () => {
  it("shows the banned message on 403", async () => {
    const user = userEvent.setup();
    mockLogin.mockRejectedValue(new ApiError(403, '{"detail":"Forbidden"}'));
    renderLogin();

    await user.type(await screen.findByPlaceholderText("Email or username"), "banned");
    await user.type(screen.getByPlaceholderText(/password/i), "s3cret-pass");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "This account has been suspended.",
    );
  });

  it("shows the rate-limit message on 429", async () => {
    const user = userEvent.setup();
    mockLogin.mockRejectedValue(new ApiError(429, '{"detail":"slow down"}'));
    renderLogin();

    await user.type(await screen.findByPlaceholderText("Email or username"), "ada");
    await user.type(screen.getByPlaceholderText(/password/i), "s3cret-pass");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/too many attempts/i);
  });

  it("shows bad-credentials text on 401", async () => {
    const user = userEvent.setup();
    mockLogin.mockRejectedValue(new ApiError(401, '{"detail":"Not authenticated"}'));
    renderLogin();

    await user.type(await screen.findByPlaceholderText("Email or username"), "ada");
    await user.type(screen.getByPlaceholderText(/password/i), "wrong-password");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid login or password.");
  });
});

describe("signup availability", () => {
  it("hides account creation unless signup_open", async () => {
    renderLogin();
    expect(await screen.findByText(/ask an admin for an invite/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /create one/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /have an invite/i })).not.toBeInTheDocument();
  });

  it("offers Create one when signup_open", async () => {
    mockConfig.signup_open = true;
    renderLogin();
    expect(await screen.findByRole("button", { name: /need an account\? create one/i })).toBeInTheDocument();
  });

  it("offers Have an invite? when signup_invite_only", async () => {
    mockConfig.signup_invite_only = true;
    renderLogin();
    expect(await screen.findByRole("button", { name: /have an invite/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /create one/i })).not.toBeInTheDocument();
  });
});

describe("invite-only sign-up flow", () => {
  it("?invite= opens sign-up prefilled and passes invite_token", async () => {
    const user = userEvent.setup();
    mockConfig.signup_invite_only = true;
    mockSearch = new URLSearchParams({ invite: "tok-123" });
    renderLogin();

    const inviteInput = await screen.findByLabelText("Invite code");
    expect(inviteInput).toHaveValue("tok-123");

    await user.type(screen.getByPlaceholderText("Email"), "ada@example.com");
    await user.type(screen.getByPlaceholderText("Username"), "ada");
    await user.type(screen.getByPlaceholderText(/password/i), "long-enough-pass");
    await user.click(screen.getByRole("button", { name: /create account/i }));

    await waitFor(() =>
      expect(mockSignup).toHaveBeenCalledWith(
        "ada@example.com",
        "ada",
        "long-enough-pass",
        "",
        "tok-123",
      ),
    );
  });

  it("Have an invite? opens the sign-up form with an invite code field", async () => {
    const user = userEvent.setup();
    mockConfig.signup_invite_only = true;
    renderLogin();

    await user.click(await screen.findByRole("button", { name: /have an invite/i }));
    expect(await screen.findByLabelText("Invite code")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Email")).toBeInTheDocument();
  });

  it("requires a code when invite-only and none was supplied", async () => {
    const user = userEvent.setup();
    mockConfig.signup_invite_only = true;
    renderLogin();

    await user.click(await screen.findByRole("button", { name: /have an invite/i }));
    await user.type(await screen.findByPlaceholderText("Email"), "ada@example.com");
    await user.type(screen.getByPlaceholderText("Username"), "ada");
    await user.type(screen.getByPlaceholderText(/password/i), "long-enough-pass");
    await user.click(screen.getByRole("button", { name: /create account/i }));

    expect(await screen.findByText("Enter your invite code.")).toBeInTheDocument();
    expect(mockSignup).not.toHaveBeenCalled();
  });
});

describe("sign-up per-field errors", () => {
  async function openSignup(user: ReturnType<typeof userEvent.setup>) {
    mockConfig.signup_open = true;
    renderLogin();
    await user.click(await screen.findByRole("button", { name: /need an account\? create one/i }));
  }

  it("validates fields client-side before submitting", async () => {
    const user = userEvent.setup();
    await openSignup(user);

    await user.type(screen.getByPlaceholderText("Email"), "not-an-email");
    await user.type(screen.getByPlaceholderText("Username"), "ab");
    await user.type(screen.getByPlaceholderText(/password/i), "short");
    await user.click(screen.getByRole("button", { name: /create account/i }));

    expect(await screen.findByText("Enter a valid email address.")).toBeInTheDocument();
    expect(screen.getByText("Username must be at least 3 characters.")).toBeInTheDocument();
    expect(screen.getByText("Password must be at least 12 characters.")).toBeInTheDocument();
    expect(mockSignup).not.toHaveBeenCalled();
  });

  it("surfaces server-side 422 details on the offending field without a form banner", async () => {
    const user = userEvent.setup();
    mockSignup.mockRejectedValue(
      new ApiError(
        422,
        JSON.stringify([
          { loc: ["body", "email"], msg: "value is not a valid email address" },
        ]),
      ),
    );
    await openSignup(user);

    await user.type(screen.getByPlaceholderText("Email"), "ada@example.com");
    await user.type(screen.getByPlaceholderText("Username"), "ada");
    await user.type(screen.getByPlaceholderText(/password/i), "long-enough-pass");
    await user.click(screen.getByRole("button", { name: /create account/i }));

    expect(await screen.findByText("value is not a valid email address")).toBeInTheDocument();
    await waitFor(() => expect(mockSignup).toHaveBeenCalled());
    expect(screen.queryByText(/could not create the account/i)).not.toBeInTheDocument();
  });

  it("rejects sign-ups closed by the server with an invite-oriented message", async () => {
    const user = userEvent.setup();
    mockSignup.mockRejectedValue(new ApiError(403, '{"detail":"signup closed"}'));
    await openSignup(user);

    await user.type(screen.getByPlaceholderText("Email"), "ada@example.com");
    await user.type(screen.getByPlaceholderText("Username"), "ada");
    await user.type(screen.getByPlaceholderText(/password/i), "long-enough-pass");
    await user.click(screen.getByRole("button", { name: /create account/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      /sign-ups are currently closed/i,
    );
  });
});
