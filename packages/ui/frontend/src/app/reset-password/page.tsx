"use client";

import { Suspense, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useMutation } from "@tanstack/react-query";
import { Loader2, LockKeyhole, ShieldCheck } from "lucide-react";
import { authApi } from "@/lib/api";
import { authErrorMessage } from "@/lib/auth-errors";

function ResetPasswordForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const token = searchParams.get("token") ?? "";
  const [newPassword, setNewPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [localError, setLocalError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  const resetMutation = useMutation({
    mutationFn: () => authApi.resetPassword(token, newPassword),
    onSuccess: () => setDone(true),
    onError: (error) => setLocalError(authErrorMessage(error, "reset")),
  });

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setLocalError(null);
    if (newPassword.length < 12) {
      setLocalError("Password must be at least 12 characters.");
      return;
    }
    if (newPassword !== confirm) {
      setLocalError("Passwords do not match.");
      return;
    }
    resetMutation.mutate();
  };

  return (
    <div className="flex-1 flex items-center justify-center p-8">
      <div className="max-w-md w-full glass rounded-2xl border border-amber-500/20 p-8 space-y-5">
        <div className="text-center">
          <h1 className="text-xl font-bold text-slate-100 flex items-center justify-center gap-2">
            <LockKeyhole className="h-5 w-5 text-amber-400" /> Set a new password
          </h1>
          <p className="mt-1 text-sm text-slate-400">
            This link is single-use and expires one hour after it was issued.
          </p>
        </div>

        {!token ? (
          <div role="alert" className="rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-300 space-y-2">
            <p>This reset link is missing its token. Request a new one.</p>
            <Link href="/forgot-password" className="text-xs text-cyan-300 underline-offset-2 hover:underline">
              Request a new link
            </Link>
          </div>
        ) : done ? (
          <div role="status" className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-3 py-3 text-sm text-emerald-200 space-y-3">
            <p className="flex items-center gap-2">
              <ShieldCheck className="h-4 w-4 flex-shrink-0" />
              Password updated. All sessions have been signed out — sign in with
              your new password.
            </p>
            <button className="btn-cyber w-full justify-center text-sm" onClick={() => router.push("/login")}>
              Go to sign in
            </button>
          </div>
        ) : (
          <form className="space-y-3" onSubmit={onSubmit} noValidate>
            {localError && (
              <div role="alert" className="rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-300">
                {localError}
              </div>
            )}
            <div>
              <input
                className="input-cyber w-full text-sm"
                placeholder="New password (min 12 characters)"
                type="password"
                required
                minLength={12}
                autoComplete="new-password"
                aria-label="New password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
              />
            </div>
            <div>
              <input
                className="input-cyber w-full text-sm"
                placeholder="Confirm new password"
                type="password"
                required
                minLength={12}
                autoComplete="new-password"
                aria-label="Confirm new password"
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
              />
            </div>
            <button
              type="submit"
              disabled={resetMutation.isPending}
              className="btn-cyber flex w-full items-center justify-center gap-2 text-sm"
            >
              {resetMutation.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <LockKeyhole className="h-4 w-4" />
              )}
              Set new password
            </button>
          </form>
        )}

        <div className="text-center text-xs text-slate-400">
          <Link href="/login" className="underline-offset-2 hover:underline">
            Back to sign in
          </Link>
        </div>
      </div>
    </div>
  );
}

export default function ResetPasswordPage() {
  return (
    <Suspense
      fallback={
        <div className="flex-1 flex items-center justify-center">
          <Loader2 className="h-6 w-6 animate-spin text-amber-400" />
        </div>
      }
    >
      <ResetPasswordForm />
    </Suspense>
  );
}
