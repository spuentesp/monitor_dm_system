"use client";

import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, LogIn, UserPlus } from "lucide-react";
import { ApiError, authApi } from "@/lib/api";

function authErrorMessage(error: unknown, mode: "login" | "signup"): string {
  const status = error instanceof ApiError ? error.status : 0;
  if (status === 429) return "Too many attempts. Please wait a minute and try again.";
  if (status === 403) return "This account has been suspended.";
  if (mode === "login") {
    if (status === 401) return "Invalid login or password.";
    return "Sign-in failed. Please try again.";
  }
  if (status === 409) return "An account with this email or username already exists.";
  if (status === 422) return "Please check the form — some fields are invalid.";
  return "Could not create the account. Please try again.";
}

const ERROR_MESSAGES: Record<string, string> = {
  invalid_state: "Sign-in session expired. Please try again.",
  oauth_failed: "Google sign-in failed. Please try again.",
  suspended: "This account has been suspended.",
};

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const queryClient = useQueryClient();
  const [mode, setMode] = useState<"login" | "signup">("login");
  const [login, setLogin] = useState("");
  const [email, setEmail] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");

  const { data: config } = useQuery({
    queryKey: ["auth-config"],
    queryFn: authApi.config,
  });

  const errorParam = searchParams.get("error");
  const oauthError = errorParam ? ERROR_MESSAGES[errorParam] ?? "Sign-in failed." : null;

  const authMutation = useMutation({
    mutationFn: () =>
      mode === "login"
        ? authApi.login(login, password)
        : authApi.signup(email, username, password, displayName),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["auth-me"] });
      router.push("/");
    },
  });

  return (
    <div className="flex-1 flex items-center justify-center p-8">
      <div className="max-w-md w-full glass rounded-2xl border border-amber-500/20 p-8 space-y-5">
        <div className="text-center">
          <h1 className="text-xl font-bold text-slate-100">MONITOR</h1>
          <p className="mt-1 text-sm text-slate-400">
            {mode === "login" ? "Sign in to your account" : "Create your account"}
          </p>
        </div>

        {oauthError && (
          <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-300">
            {oauthError}
          </div>
        )}
        {authMutation.isError && (
          <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-300">
            {authErrorMessage(authMutation.error, mode)}
          </div>
        )}

        {config?.google_oauth && !config.auth_disabled && (
          <>
            <a
              href={authApi.googleLoginUrl()}
              className="btn-ghost flex w-full items-center justify-center gap-2 text-sm"
            >
              <svg viewBox="0 0 24 24" className="h-4 w-4" aria-hidden>
                <path fill="#4285F4" d="M23.5 12.3c0-.9-.1-1.5-.3-2.2H12v4.1h6.5c-.1 1.1-.8 2.7-2.4 3.8l3.7 2.9c2.3-2.1 3.7-5.2 3.7-8.6z" />
                <path fill="#34A853" d="M12 24c3.2 0 5.9-1.1 7.9-2.9l-3.7-2.9c-1 .7-2.4 1.2-4.2 1.2-3.2 0-5.9-2.1-6.8-5.1L1.3 17.2C3.3 21.2 7.3 24 12 24z" />
                <path fill="#FBBC05" d="M5.2 14.3c-.2-.7-.4-1.5-.4-2.3s.2-1.6.4-2.3L1.3 6.8C.5 8.4 0 10.1 0 12s.5 3.6 1.3 5.2l3.9-2.9z" />
                <path fill="#EA4335" d="M12 4.7c1.8 0 3 .8 3.7 1.4l3.3-3.2C17.9 1.1 15.2 0 12 0 7.3 0 3.3 2.8 1.3 6.8l3.9 2.9c.9-3 3.6-5 6.8-5z" />
              </svg>
              Continue with Google
            </a>
            <div className="flex items-center gap-3 text-xs text-slate-500">
              <div className="h-px flex-1 bg-slate-700/60" />
              or
              <div className="h-px flex-1 bg-slate-700/60" />
            </div>
          </>
        )}

        <form
          className="space-y-3"
          onSubmit={(e) => {
            e.preventDefault();
            authMutation.mutate();
          }}
        >
          {mode === "signup" && (
            <>
              <input
                className="input-cyber w-full text-sm"
                placeholder="Email"
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
              <input
                className="input-cyber w-full text-sm"
                placeholder="Username"
                required
                minLength={3}
                maxLength={50}
                pattern="[A-Za-z0-9_.-]+"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
              />
              <input
                className="input-cyber w-full text-sm"
                placeholder="Display name (optional)"
                maxLength={200}
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
              />
            </>
          )}
          {mode === "login" && (
            <input
              className="input-cyber w-full text-sm"
              placeholder="Email or username"
              required
              value={login}
              onChange={(e) => setLogin(e.target.value)}
            />
          )}
          <input
            className="input-cyber w-full text-sm"
            placeholder={mode === "signup" ? "Password (min 12 characters)" : "Password"}
            type="password"
            required
            minLength={mode === "signup" ? 12 : 1}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          <button
            type="submit"
            disabled={authMutation.isPending}
            className="btn-cyber flex w-full items-center justify-center gap-2 text-sm"
          >
            {authMutation.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : mode === "login" ? (
              <LogIn className="h-4 w-4" />
            ) : (
              <UserPlus className="h-4 w-4" />
            )}
            {mode === "login" ? "Sign in" : "Create account"}
          </button>
        </form>

        {!config?.auth_disabled && (
          <button
            className="w-full text-center text-xs text-slate-400 underline-offset-2 hover:underline"
            onClick={() => setMode(mode === "login" ? "signup" : "login")}
          >
            {mode === "login" ? "Need an account? Create one" : "Already have an account? Sign in"}
          </button>
        )}
      </div>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense
      fallback={
        <div className="flex-1 flex items-center justify-center">
          <Loader2 className="h-6 w-6 animate-spin text-amber-400" />
        </div>
      }
    >
      <LoginForm />
    </Suspense>
  );
}
