"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Eye, EyeOff, Loader2, LogIn, UserPlus } from "lucide-react";
import { ApiError, authApi } from "@/lib/api";
import {
  authErrorMessage,
  sanitizeNextPath,
  signUpFieldErrors,
  type AuthFieldErrors,
} from "@/lib/auth-errors";

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const USERNAME_RE = /^[A-Za-z0-9_.-]+$/;

function validateSignup(fields: {
  email: string;
  username: string;
  password: string;
  inviteCode: string;
  inviteOnly: boolean;
}): AuthFieldErrors {
  const errs: AuthFieldErrors = {};
  if (!fields.email.trim()) errs.email = "Email is required.";
  else if (!EMAIL_RE.test(fields.email.trim())) errs.email = "Enter a valid email address.";
  if (!fields.username.trim()) errs.username = "Username is required.";
  else if (fields.username.trim().length < 3) errs.username = "Username must be at least 3 characters.";
  else if (fields.username.length > 50) errs.username = "Username must be 50 characters or fewer.";
  else if (!USERNAME_RE.test(fields.username)) errs.username = "Only letters, numbers, _ . and - are allowed.";
  if (fields.password.length < 12) errs.password = "Password must be at least 12 characters.";
  if (fields.inviteOnly && !fields.inviteCode.trim()) errs.invite = "Enter your invite code.";
  return errs;
}

function FieldError({ message }: { message?: string }) {
  if (!message) return null;
  return (
    <p role="alert" className="mt-1 text-xs text-red-300">
      {message}
    </p>
  );
}

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const queryClient = useQueryClient();

  const inviteParam = searchParams.get("invite");
  const [mode, setMode] = useState<"login" | "signup">(inviteParam ? "signup" : "login");
  const [login, setLogin] = useState("");
  const [email, setEmail] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [inviteCode, setInviteCode] = useState(inviteParam ?? "");
  const [showPassword, setShowPassword] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<AuthFieldErrors>({});
  const [formError, setFormError] = useState<string | null>(null);

  const safeNext = useMemo(
    () => sanitizeNextPath(searchParams.get("next")) ?? "/",
    [searchParams],
  );

  const { data: config } = useQuery({
    queryKey: ["auth-config"],
    queryFn: authApi.config,
  });

  const signupOpen = !!config?.signup_open;
  const inviteOnly = !!config?.signup_invite_only;
  const canCreateAccount = signupOpen || inviteOnly;

  // Sign-ups are closed (MONITOR_SIGNUP_MODE=closed): never leave the form
  // sitting in sign-up mode, even when someone deep-linked with ?invite=.
  useEffect(() => {
    if (config && mode === "signup" && !canCreateAccount) setMode("login");
  }, [config, mode, canCreateAccount]);

  const errorParam = searchParams.get("error");
  const oauthError = errorParam
    ? ERROR_MESSAGES[errorParam] ?? "Sign-in failed."
    : null;
  const banner = oauthError ?? formError;

  const clearField = (field: keyof AuthFieldErrors) =>
    setFieldErrors((prev) => {
      if (!prev[field]) return prev;
      const next = { ...prev };
      delete next[field];
      return next;
    });

  const authMutation = useMutation({
    mutationFn: () => {
      if (mode === "login") return authApi.login(login, password);
      return authApi.signup(
        email.trim(),
        username.trim(),
        password,
        displayName.trim(),
        inviteCode.trim() || undefined,
      );
    },
    onSuccess: async () => {
      setFormError(null);
      setFieldErrors({});
      await queryClient.invalidateQueries({ queryKey: ["auth-me"] });
      router.push(safeNext);
    },
    onError: (error) => {
      const errs = mode === "signup" ? signUpFieldErrors(error) : null;
      setFieldErrors(errs ?? {});
      const status = error instanceof ApiError ? error.status : 0;
      const statusWarrantsBanner = status === 403 || status === 429;
      const showBanner = statusWarrantsBanner || !errs || Object.keys(errs).length === 0;
      setFormError(showBanner ? authErrorMessage(error, mode) : null);
    },
  });

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);
    if (mode === "signup") {
      const errs = validateSignup({
        email,
        username,
        password,
        inviteCode,
        inviteOnly,
      });
      setFieldErrors(errs);
      if (Object.keys(errs).length > 0) return;
    }
    authMutation.mutate();
  };

  return (
    <div className="flex-1 flex items-center justify-center p-8">
      <div className="max-w-md w-full glass rounded-2xl border border-amber-500/20 p-8 space-y-5">
        <div className="text-center">
          <h1 className="text-xl font-bold text-slate-100">MONITOR</h1>
          <p className="mt-1 text-sm text-slate-400">
            {mode === "login" ? "Sign in to your account" : "Create your account"}
          </p>
          {mode === "signup" && inviteOnly && inviteParam && (
            <p className="mt-2 text-xs text-cyan-300/90">Invite code applied — finish signing up below.</p>
          )}
        </div>

        {banner && (
          <div
            role="alert"
            className="rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-300"
          >
            {banner}
          </div>
        )}
        {config && mode === "signup" && !canCreateAccount && (
          <div
            role="alert"
            className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-sm text-amber-300"
          >
            Sign-ups are currently closed.
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

        <form className="space-y-3" onSubmit={onSubmit} noValidate>
          {mode === "signup" && (
            <>
              <div>
                <input
                  className="input-cyber w-full text-sm"
                  placeholder="Email"
                  type="email"
                  required
                  autoComplete="email"
                  aria-invalid={!!fieldErrors.email}
                  value={email}
                  onChange={(e) => {
                    setEmail(e.target.value);
                    clearField("email");
                  }}
                />
                <FieldError message={fieldErrors.email} />
              </div>
              <div>
                <input
                  className="input-cyber w-full text-sm"
                  placeholder="Username"
                  required
                  minLength={3}
                  maxLength={50}
                  pattern="[A-Za-z0-9_.-]+"
                  autoComplete="username"
                  aria-invalid={!!fieldErrors.username}
                  value={username}
                  onChange={(e) => {
                    setUsername(e.target.value);
                    clearField("username");
                  }}
                />
                <FieldError message={fieldErrors.username} />
              </div>
              <div>
                <input
                  className="input-cyber w-full text-sm"
                  placeholder="Display name (optional)"
                  maxLength={200}
                  value={displayName}
                  onChange={(e) => setDisplayName(e.target.value)}
                />
              </div>
              {(inviteOnly || inviteCode) && (
                <div>
                  <input
                    className="input-cyber w-full text-sm font-mono"
                    placeholder="Invite code"
                    aria-label="Invite code"
                    aria-invalid={!!fieldErrors.invite}
                    value={inviteCode}
                    onChange={(e) => {
                      setInviteCode(e.target.value);
                      clearField("invite");
                    }}
                  />
                  <FieldError message={fieldErrors.invite} />
                </div>
              )}
            </>
          )}
          {mode === "login" && (
            <div>
              <input
                className="input-cyber w-full text-sm"
                placeholder="Email or username"
                required
                autoComplete="username"
                value={login}
                onChange={(e) => setLogin(e.target.value)}
              />
            </div>
          )}
          <div>
            <div className="relative">
              <input
                className="input-cyber w-full text-sm pr-10"
                placeholder={mode === "signup" ? "Password (min 12 characters)" : "Password"}
                type={showPassword ? "text" : "password"}
                required
                minLength={mode === "signup" ? 12 : 1}
                autoComplete={mode === "signup" ? "new-password" : "current-password"}
                aria-invalid={!!fieldErrors.password}
                value={password}
                onChange={(e) => {
                  setPassword(e.target.value);
                  clearField("password");
                }}
              />
              <button
                type="button"
                onClick={() => setShowPassword((v) => !v)}
                aria-label={showPassword ? "Hide password" : "Show password"}
                title={showPassword ? "Hide password" : "Show password"}
                className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-slate-500 hover:text-slate-300 transition-colors"
              >
                {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            </div>
            <FieldError message={fieldErrors.password} />
          </div>

          {mode === "login" && (
            <div className="text-right">
              <Link
                href="/forgot-password"
                className="text-xs text-slate-400 underline-offset-2 hover:underline"
              >
                Forgot password?
              </Link>
            </div>
          )}

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
          <div className="space-y-2 text-center text-xs text-slate-400">
            {mode === "login" && signupOpen && (
              <button
                className="w-full text-center underline-offset-2 hover:underline"
                onClick={() => {
                  setMode("signup");
                  setFormError(null);
                  setFieldErrors({});
                }}
              >
                Need an account? Create one
              </button>
            )}
            {mode === "login" && inviteOnly && (
              <button
                className="w-full text-center underline-offset-2 hover:underline"
                onClick={() => {
                  setMode("signup");
                  setFormError(null);
                  setFieldErrors({});
                }}
              >
                Have an invite?
              </button>
            )}
            {mode === "login" && !canCreateAccount && config && (
              <p className="text-slate-500">Don&apos;t have an account? Ask an admin for an invite.</p>
            )}
            {mode === "signup" && (
              <button
                className="w-full text-center underline-offset-2 hover:underline"
                onClick={() => {
                  setMode("login");
                  setFormError(null);
                  setFieldErrors({});
                }}
              >
                Already have an account? Sign in
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

const ERROR_MESSAGES: Record<string, string> = {
  invalid_state: "Sign-in session expired. Please try again.",
  oauth_failed: "Google sign-in failed. Please try again.",
  suspended: "This account has been suspended.",
};

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
