// @vitest-environment happy-dom
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

type MockConfig = { auth_disabled: boolean; google_oauth: boolean; signup_open: boolean; signup_invite_only: boolean; email_reset: boolean };
let mockConfig: MockConfig;
const mockForgot = vi.fn();

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    authApi: {
      config: () => Promise.resolve(mockConfig),
      forgotPassword: (login: string) => mockForgot(login),
    },
  };
});

import ForgotPasswordPage from "./page";
import { ApiError } from "@/lib/api";

function renderForgot() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ForgotPasswordPage />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mockConfig = { auth_disabled: false, google_oauth: false, signup_open: false, signup_invite_only: true, email_reset: true };
  mockForgot.mockResolvedValue({ ok: true });
});

describe("/forgot-password", () => {
  it("tells the user to ask their admin when email reset is not configured", async () => {
    mockConfig.email_reset = false;
    renderForgot();
    expect(await screen.findByText(/ask your admin for a reset link/i)).toBeInTheDocument();
    expect(screen.queryByPlaceholderText("Email or username")).not.toBeInTheDocument();
    expect(mockForgot).not.toHaveBeenCalled();
  });

  it("submits the login and shows the enumeration-safe confirmation", async () => {
    const user = userEvent.setup();
    renderForgot();

    await user.type(await screen.findByPlaceholderText("Email or username"), "ada");
    await user.click(screen.getByRole("button", { name: /send reset link/i }));

    expect(await screen.findByRole("status")).toHaveTextContent(
      /if an account exists for that address/i,
    );
    expect(mockForgot).toHaveBeenCalledWith("ada");
  });

  it("shows the rate-limit message on 429", async () => {
    const user = userEvent.setup();
    mockForgot.mockRejectedValue(new ApiError(429, '{"detail":"slow down"}'));
    renderForgot();

    await user.type(await screen.findByPlaceholderText("Email or username"), "ada");
    await user.click(screen.getByRole("button", { name: /send reset link/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/too many attempts/i);
    await waitFor(() => expect(mockForgot).toHaveBeenCalled());
  });

  it("links back to sign in", async () => {
    renderForgot();
    const links = await screen.findAllByRole("link", { name: /back to sign in/i });
    expect(links[0]).toHaveAttribute("href", "/login");
  });
});
