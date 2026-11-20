"use client";

import { useState } from "react";
import Link from "next/link";
import { useMutation, useQuery } from "@tanstack/react-query";
import { KeyRound, Loader2, MailCheck } from "lucide-react";
import { ApiError, authApi } from "@/lib/api";
import { authErrorMessage } from "@/lib/auth-errors";

export default function ForgotPasswordPage() {
  const [login, setLogin] = useState("");
  const [sent, setSent] = useState(false);

  const { data: config } = useQuery({
    queryKey: ["auth-config"],
    queryFn: authApi.config,
  });

  const forgotMutation = useMutation({
    mutationFn: () => authApi.forgotPassword(login.trim()),
    onSuccess: () => setSent(true),
  });

  const emailReset = !!config?.email_reset;

  return (
    <div className="flex-1 flex items-center justify-center p-8">
      <div className="max-w-md w-full glass rounded-2xl border border-amber-500/20 p-8 space-y-5">
        <div className="text-center">
          <h1 className="text-xl font-bold text-slate-100 flex items-center justify-center gap-2">
            <KeyRound className="h-5 w-5 text-amber-400" /> Forgot password
          </h1>
          <p className="mt-1 text-sm text-slate-400">
            We&apos;ll send a one-time reset link to your account.
          </p>
        </div>

        {config && !emailReset ? (
          <div
            role="alert"
            className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-3 text-sm text-amber-200 space-y-2"
          >
            <p>
              Email reset isn&apos;t enabled on this instance. Ask your admin for a
              reset link instead — they can issue one from the Admin page.
            </p>
            <Link href="/login" className="inline-block text-xs text-cyan-300 underline-offset-2 hover:underline">
              Back to sign in
            </Link>
          </div>
        ) : sent ? (
          <div
            role="status"
            className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-3 py-3 text-sm text-emerald-200 space-y-2"
          >
            <p className="flex items-center gap-2">
              <MailCheck className="h-4 w-4 flex-shrink-0" />
              If an account exists for that address, a reset email is on its way.
              The link expires in one hour.
            </p>
            <Link href="/login" className="inline-block text-xs text-cyan-300 underline-offset-2 hover:underline">
              Back to sign in
            </Link>
          </div>
        ) : (
          <form
            className="space-y-3"
            onSubmit={(e) => {
              e.preventDefault();
              forgotMutation.mutate();
            }}
          >
            {forgotMutation.isError && (
              <div role="alert" className="rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-300">
                {authErrorMessage(forgotMutation.error, "forgot")}
              </div>
            )}
            <input
              className="input-cyber w-full text-sm"
              placeholder="Email or username"
              required
              autoComplete="username"
              value={login}
              onChange={(e) => setLogin(e.target.value)}
            />
            <button
              type="submit"
              disabled={forgotMutation.isPending || !login.trim()}
              className="btn-cyber flex w-full items-center justify-center gap-2 text-sm"
            >
              {forgotMutation.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <KeyRound className="h-4 w-4" />
              )}
              Send reset link
            </button>
          </form>
        )}

        {config && emailReset && !sent && (
          <p className="text-center text-xs text-slate-500">
            The link works for one hour and signs out all your sessions once used.
          </p>
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
