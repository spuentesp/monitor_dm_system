// @vitest-environment happy-dom
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

let mockSearch = new URLSearchParams();
const mockPush = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush, replace: vi.fn() }),
  usePathname: () => "/reset-password",
  useSearchParams: () => mockSearch,
}));

const mockReset = vi.fn();

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    authApi: {
      resetPassword: (token: string, new_password: string) => mockReset(token, new_password),
    },
  };
});

import ResetPasswordPage from "./page";
import { ApiError } from "@/lib/api";

function renderReset() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ResetPasswordPage />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mockSearch = new URLSearchParams({ token: "reset-tok" });
  mockReset.mockResolvedValue({ ok: true });
});

describe("/reset-password", () => {
  it("asks for a new link when the token is missing", async () => {
    mockSearch = new URLSearchParams();
    renderReset();
    expect(await screen.findByText(/missing its token/i)).toBeInTheDocument();
    expect(screen.queryByLabelText("New password")).not.toBeInTheDocument();
  });

  it("rejects mismatched passwords client-side without calling the API", async () => {
    const user = userEvent.setup();
    renderReset();

    await user.type(await screen.findByLabelText("New password"), "long-enough-pass");
    await user.type(screen.getByLabelText("Confirm new password"), "different-pass");
    await user.click(screen.getByRole("button", { name: /set new password/i }));

    expect(await screen.findByText("Passwords do not match.")).toBeInTheDocument();
    expect(mockReset).not.toHaveBeenCalled();
  });

  it("submits token + new password and confirms the reset", async () => {
    const user = userEvent.setup();
    renderReset();

    await user.type(await screen.findByLabelText("New password"), "long-enough-pass");
    await user.type(screen.getByLabelText("Confirm new password"), "long-enough-pass");
    await user.click(screen.getByRole("button", { name: /set new password/i }));

    await waitFor(() => expect(mockReset).toHaveBeenCalledWith("reset-tok", "long-enough-pass"));
    expect(await screen.findByRole("status")).toHaveTextContent(/all sessions have been signed out/i);
    expect(screen.getByRole("button", { name: /go to sign in/i })).toBeInTheDocument();
  });

  it("reports an expired or used token distinctly", async () => {
    const user = userEvent.setup();
    mockReset.mockRejectedValue(new ApiError(410, '{"detail":"token expired"}'));
    renderReset();

    await user.type(await screen.findByLabelText("New password"), "long-enough-pass");
    await user.type(screen.getByLabelText("Confirm new password"), "long-enough-pass");
    await user.click(screen.getByRole("button", { name: /set new password/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      /invalid or has expired/i,
    );
  });

  it("requires at least 12 characters", async () => {
    const user = userEvent.setup();
    renderReset();

    await user.type(await screen.findByLabelText("New password"), "short");
    await user.type(screen.getByLabelText("Confirm new password"), "short");
    await user.click(screen.getByRole("button", { name: /set new password/i }));

    expect(await screen.findByText(/at least 12 characters/i)).toBeInTheDocument();
    expect(mockReset).not.toHaveBeenCalled();
  });
});
