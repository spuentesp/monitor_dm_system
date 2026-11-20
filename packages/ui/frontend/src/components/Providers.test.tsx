// @vitest-environment happy-dom
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useQueryClient } from "@tanstack/react-query";

let mockPathname = "/forge";
const mockReplace = vi.fn();

vi.mock("next/navigation", () => ({
  usePathname: () => mockPathname,
  useRouter: () => ({ push: vi.fn(), replace: mockReplace }),
}));

let meBehavior: () => Promise<unknown>;

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    authApi: {
      me: () => meBehavior(),
    },
  };
});

import Providers, { isPublicAuthPath } from "./Providers";
import { ApiError } from "@/lib/api";

const SESSION = {
  auth_disabled: false,
  user: { id: "u", email: "a@b.c", username: "ada", display_name: "Ada", is_admin: false, created_at: "", updated_at: "" },
};

function InvalidateMe() {
  const qc = useQueryClient();
  return (
    <button onClick={() => qc.invalidateQueries({ queryKey: ["auth-me"] })}>refetch-me</button>
  );
}

function renderProviders() {
  return render(
    <Providers>
      <div data-testid="child">child content</div>
      <InvalidateMe />
    </Providers>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mockPathname = "/forge";
  meBehavior = () => Promise.resolve(SESSION);
  window.history.replaceState({}, "", "/");
});

describe("isPublicAuthPath", () => {
  it("marks the auth pages public and everything else not", () => {
    expect(isPublicAuthPath("/login")).toBe(true);
    expect(isPublicAuthPath("/login/callback")).toBe(true);
    expect(isPublicAuthPath("/forgot-password")).toBe(true);
    expect(isPublicAuthPath("/reset-password")).toBe(true);
    expect(isPublicAuthPath("/forge")).toBe(false);
    expect(isPublicAuthPath("/")).toBe(false);
  });
});

describe("AuthGate", () => {
  it("renders a skeleton instead of blank while the session loads", () => {
    meBehavior = () => new Promise(() => {});
    renderProviders();
    expect(screen.getByRole("status")).toBeInTheDocument();
    expect(screen.queryByTestId("child")).not.toBeInTheDocument();
  });

  it("renders children once the session resolves", async () => {
    renderProviders();
    expect(await screen.findByTestId("child")).toBeInTheDocument();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("redirects to /login?next=<path> on a cold 401", async () => {
    mockPathname = "/forge";
    window.history.replaceState({}, "", "/forge?tab=x");
    meBehavior = () => Promise.reject(new ApiError(401, '{"detail":"Not authenticated"}'));
    renderProviders();

    await waitFor(() =>
      expect(mockReplace).toHaveBeenCalledWith(
        `/login?next=${encodeURIComponent("/forge?tab=x")}`,
      ),
    );
    expect(screen.queryByTestId("child")).not.toBeInTheDocument();
    expect(screen.getByRole("status")).toBeInTheDocument();
    // Cold 401 was never a session — no expiry toast.
    expect(screen.queryByText(/session has expired/i)).not.toBeInTheDocument();
  });

  it("does not redirect public auth pages on 401", async () => {
    mockPathname = "/forgot-password";
    meBehavior = () => Promise.reject(new ApiError(401, '{"detail":"Not authenticated"}'));
    renderProviders();

    expect(await screen.findByTestId("child")).toBeInTheDocument();
    expect(mockReplace).not.toHaveBeenCalled();
  });

  it("toasts session-expired and preserves the path when the session dies", async () => {
    const user = userEvent.setup();
    mockPathname = "/gm";
    renderProviders();
    expect(await screen.findByTestId("child")).toBeInTheDocument();

    // Session dies on the next refetch.
    meBehavior = () => Promise.reject(new ApiError(401, '{"detail":"Not authenticated"}'));
    await user.click(screen.getByRole("button", { name: "refetch-me" }));

    expect(await screen.findByText(/session has expired/i)).toBeInTheDocument();
    await waitFor(() =>
      expect(mockReplace).toHaveBeenCalledWith(`/login?next=${encodeURIComponent("/gm")}`),
    );
    expect(screen.queryByTestId("child")).not.toBeInTheDocument();
  });
});
