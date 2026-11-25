"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Copy,
  KeyRound,
  Laptop,
  Loader2,
  LogOut,
  Plus,
  ShieldCheck,
  UserRound,
  XCircle,
} from "lucide-react";
import { ApiError, authApi, type ApiToken } from "@/lib/api";
import { authErrorMessage } from "@/lib/auth-errors";
import { useNotify } from "@/components/NotificationProvider";
import { PageSkeleton } from "@/components/PageSkeleton";
import { CopyValueDialog } from "@/components/CopyValueDialog";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { formatRelativeTime } from "@/lib/utils";

function SectionCard({
  title,
  icon: Icon,
  description,
  children,
}: {
  title: string;
  icon: React.ElementType;
  description?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="glass rounded-2xl border border-white/10 p-5 space-y-4">
      <div className="flex items-center gap-2.5">
        <Icon className="h-4 w-4 text-cyan-400" />
        <div>
          <h2 className="text-sm font-semibold text-slate-100">{title}</h2>
          {description && <p className="text-xs text-slate-500 mt-0.5">{description}</p>}
        </div>
      </div>
      {children}
    </section>
  );
}

function ChangePasswordCard() {
  const { notify } = useNotify();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: () => authApi.changePassword(current, next),
    onSuccess: () => {
      setCurrent("");
      setNext("");
      setConfirm("");
      setError(null);
      notify("success", "Password updated. Other sessions were signed out.");
    },
    onError: (err) => {
      if (err instanceof ApiError && err.status === 401) {
        setError("Current password is incorrect.");
      } else {
        setError(authErrorMessage(err, "login"));
      }
    },
  });

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (next.length < 12) {
      setError("New password must be at least 12 characters.");
      return;
    }
    if (next !== confirm) {
      setError("New passwords do not match.");
      return;
    }
    mutation.mutate();
  };

  return (
    <SectionCard title="Change password" icon={KeyRound} description="Changing your password signs out your other sessions.">
      <form className="space-y-3 max-w-md" onSubmit={submit} noValidate>
        {error && (
          <div role="alert" className="rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-300">
            {error}
          </div>
        )}
        <input
          className="input-cyber w-full text-sm"
          type="password"
          placeholder="Current password"
          autoComplete="current-password"
          aria-label="Current password"
          required
          value={current}
          onChange={(e) => setCurrent(e.target.value)}
        />
        <input
          className="input-cyber w-full text-sm"
          type="password"
          placeholder="New password (min 12 characters)"
          autoComplete="new-password"
          aria-label="New password"
          required
          minLength={12}
          value={next}
          onChange={(e) => setNext(e.target.value)}
        />
        <input
          className="input-cyber w-full text-sm"
          type="password"
          placeholder="Confirm new password"
          autoComplete="new-password"
          aria-label="Confirm new password"
          required
          minLength={12}
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
        />
        <button type="submit" disabled={mutation.isPending} className="btn-cyber text-xs gap-1.5">
          {mutation.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <KeyRound className="h-3.5 w-3.5" />}
          Update password
        </button>
      </form>
    </SectionCard>
  );
}

function SessionsCard() {
  const router = useRouter();
  const qc = useQueryClient();
  const { notify } = useNotify();
  const [confirmAll, setConfirmAll] = useState(false);
  const [pendingRevoke, setPendingRevoke] = useState<string | null>(null);

  const sessionsQuery = useQuery({
    queryKey: ["auth-sessions"],
    queryFn: authApi.listSessions,
  });

  const revokeOne = useMutation({
    mutationFn: (prefix: string) => authApi.revokeSession(prefix),
    onSuccess: (_data, prefix) => {
      const wasCurrent = sessionsQuery.data?.sessions.find((s) => s.token_hash_prefix === prefix)?.current;
      setPendingRevoke(null);
      if (wasCurrent) {
        qc.clear();
        router.push("/login");
        return;
      }
      notify("success", "Session revoked.");
      qc.invalidateQueries({ queryKey: ["auth-sessions"] });
    },
    onError: (err) => notify("error", authErrorMessage(err, "login")),
  });

  const revokeAll = useMutation({
    mutationFn: () => authApi.revokeAllSessions(),
    onSuccess: () => {
      qc.clear();
      router.push("/login");
    },
    onError: (err) => {
      setConfirmAll(false);
      notify("error", authErrorMessage(err, "login"));
    },
  });

  const sessions = sessionsQuery.data?.sessions ?? [];

  return (
    <SectionCard
      title="Active sessions"
      icon={Laptop}
      description="Browser sessions signed in with your account."
    >
      <div className="flex justify-end">
        <button
          type="button"
          className="btn-ghost text-xs text-red-300 gap-1.5"
          onClick={() => setConfirmAll(true)}
          disabled={sessions.length === 0}
        >
          <LogOut className="h-3.5 w-3.5" /> Sign out everywhere
        </button>
      </div>

      {sessionsQuery.isLoading ? (
        <Loader2 className="h-4 w-4 animate-spin text-slate-500" data-testid="sessions-loading" />
      ) : sessions.length === 0 ? (
        <p className="text-xs text-slate-500">No active sessions found.</p>
      ) : (
        <ul className="divide-y divide-white/5 border border-white/5 rounded-xl overflow-hidden">
          {sessions.map((s) => (
            <li key={s.token_hash_prefix} className="flex items-center gap-3 px-4 py-3 text-xs">
              <Laptop className="h-3.5 w-3.5 text-slate-500 flex-shrink-0" />
              <div className="flex-1 min-w-0 space-y-0.5">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-slate-300">{s.token_hash_prefix}…</span>
                  {s.current && (
                    <span className="rounded-full border border-cyan-500/30 bg-cyan-500/10 px-1.5 py-px text-[10px] text-cyan-300">
                      current
                    </span>
                  )}
                </div>
                <p className="text-slate-500">
                  Created {formatRelativeTime(s.created_at)} · last seen {formatRelativeTime(s.last_seen_at)} ·
                  expires {formatRelativeTime(s.expires_at)}
                </p>
              </div>
              <button
                type="button"
                className="btn-ghost text-[11px] text-red-300"
                onClick={() => setPendingRevoke(s.token_hash_prefix)}
              >
                {s.current ? "Sign out" : "Revoke"}
              </button>
            </li>
          ))}
        </ul>
      )}

      {pendingRevoke && (
        <ConfirmDialog
          title="Revoke session"
          icon={XCircle}
          message="Revoke this session? The device it belongs to will be signed out."
          confirmLabel={sessions.find((s) => s.token_hash_prefix === pendingRevoke)?.current ? "Sign out" : "Revoke"}
          danger
          busy={revokeOne.isPending}
          onConfirm={() => revokeOne.mutate(pendingRevoke)}
          onClose={() => setPendingRevoke(null)}
        />
      )}

      {confirmAll && (
        <ConfirmDialog
          title="Sign out everywhere"
          icon={LogOut}
          message="This revokes every session, including this one — you will need to sign in again on every device."
          confirmLabel="Sign out everywhere"
          danger
          busy={revokeAll.isPending}
          onConfirm={() => revokeAll.mutate()}
          onClose={() => setConfirmAll(false)}
        />
      )}
    </SectionCard>
  );
}

function TokensCard() {
  const qc = useQueryClient();
  const { notify } = useNotify();
  const [name, setName] = useState("");
  const [days, setDays] = useState("");
  const [freshToken, setFreshToken] = useState<{ token: string; name: string } | null>(null);

  const tokensQuery = useQuery({
    queryKey: ["auth-tokens"],
    queryFn: authApi.listTokens,
  });

  const createMutation = useMutation({
    mutationFn: () => {
      const daysNum = Number(days);
      const expires =
        days.trim() && Number.isFinite(daysNum) && daysNum > 0
          ? new Date(Date.now() + daysNum * 24 * 3600 * 1000).toISOString()
          : null;
      return authApi.createToken(name.trim(), expires);
    },
    onSuccess: (created) => {
      setFreshToken({ token: created.token, name: created.name });
      setName("");
      setDays("");
      qc.invalidateQueries({ queryKey: ["auth-tokens"] });
    },
    onError: (err) => notify("error", authErrorMessage(err, "login")),
  });

  const revokeMutation = useMutation({
    mutationFn: (tokenId: string) => authApi.revokeToken(tokenId),
    onSuccess: () => {
      notify("success", "API token revoked.");
      qc.invalidateQueries({ queryKey: ["auth-tokens"] });
    },
    onError: (err) => notify("error", authErrorMessage(err, "login")),
  });

  const tokens = tokensQuery.data ?? [];

  return (
    <SectionCard
      title="API tokens"
      icon={ShieldCheck}
      description="Tokens authenticate scripts and CLI clients as you. A new token's value is shown once."
    >
      <form
        className="flex flex-wrap items-end gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          if (!name.trim()) return;
          createMutation.mutate();
        }}
      >
        <div className="space-y-1 min-w-48">
          <label className="text-xs text-slate-500" htmlFor="token-name">
            Name
          </label>
          <input
            id="token-name"
            className="input-cyber w-full text-sm"
            placeholder="e.g. CLI laptop"
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </div>
        <div className="space-y-1 w-36">
          <label className="text-xs text-slate-500" htmlFor="token-expiry">
            Expires in (days)
          </label>
          <input
            id="token-expiry"
            className="input-cyber w-full text-sm"
            type="number"
            min={1}
            placeholder="never"
            value={days}
            onChange={(e) => setDays(e.target.value)}
          />
        </div>
        <button type="submit" className="btn-cyber text-xs gap-1.5" disabled={createMutation.isPending || !name.trim()}>
          {createMutation.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Plus className="h-3.5 w-3.5" />}
          Create token
        </button>
      </form>

      {tokensQuery.isLoading ? (
        <Loader2 className="h-4 w-4 animate-spin text-slate-500" data-testid="tokens-loading" />
      ) : tokens.length === 0 ? (
        <p className="text-xs text-slate-500">No API tokens yet.</p>
      ) : (
        <ul className="divide-y divide-white/5 border border-white/5 rounded-xl overflow-hidden">
          {tokens.map((t: ApiToken) => (
            <li key={t.id} className="flex items-center gap-3 px-4 py-3 text-xs">
              <KeyRound className="h-3.5 w-3.5 text-slate-500 flex-shrink-0" />
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="font-medium text-slate-200">{t.name}</span>
                  <span className="font-mono text-slate-500">{t.token_prefix}…</span>
                  {t.revoked_at && (
                    <span className="rounded-full border border-slate-600 bg-white/5 px-1.5 py-px text-[10px] text-slate-400">
                      revoked
                    </span>
                  )}
                </div>
                <p className="text-slate-500 mt-0.5">
                  Created {formatRelativeTime(t.created_at)}
                  {t.expires_at && ` · expires ${formatRelativeTime(t.expires_at)}`}
                  {t.last_used_at && ` · last used ${formatRelativeTime(t.last_used_at)}`}
                </p>
              </div>
              {!t.revoked_at && (
                <button
                  type="button"
                  className="btn-ghost text-[11px] text-red-300 gap-1"
                  onClick={() => revokeMutation.mutate(t.id)}
                  disabled={revokeMutation.isPending}
                >
                  <XCircle className="h-3 w-3" /> Revoke
                </button>
              )}
            </li>
          ))}
        </ul>
      )}

      {freshToken && (
        <CopyValueDialog
          title="API token created"
          icon={Copy}
          label={`Token for “${freshToken.name}” — copy it now, it will not be shown again.`}
          value={freshToken.token}
          hint="Keep it secret. Revoke it here if it ever leaks."
          onClose={() => setFreshToken(null)}
        />
      )}
    </SectionCard>
  );
}

export default function AccountPage() {
  const { data: me, isLoading } = useQuery({
    queryKey: ["auth-me"],
    queryFn: authApi.me,
    retry: false,
    staleTime: 60_000,
  });

  if (isLoading || !me) return <PageSkeleton rows={5} />;

  const user = me.user;

  return (
    <div className="flex-1 overflow-y-auto p-6">
      <div className="mx-auto max-w-3xl space-y-5">
        <div>
          <h1 className="text-xl font-bold text-slate-100 flex items-center gap-2">
            <UserRound className="h-5 w-5 text-cyan-400" /> Account
          </h1>
          <p className="mt-1 text-sm text-slate-400">Your profile, password, sessions and API tokens.</p>
        </div>

        <SectionCard title="Profile" icon={UserRound}>
          <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-3 text-sm">
            <div>
              <dt className="text-xs text-slate-500">Display name</dt>
              <dd className="text-slate-200">{user.display_name || "—"}</dd>
            </div>
            <div>
              <dt className="text-xs text-slate-500">Username</dt>
              <dd className="text-slate-200 font-mono">{user.username}</dd>
            </div>
            <div>
              <dt className="text-xs text-slate-500">Email</dt>
              <dd className="text-slate-200">{user.email}</dd>
            </div>
            <div>
              <dt className="text-xs text-slate-500">Role</dt>
              <dd>
                {user.is_admin ? (
                  <span className="inline-flex items-center gap-1 text-amber-300 text-xs">
                    <ShieldCheck className="h-3.5 w-3.5" /> admin
                  </span>
                ) : (
                  <span className="text-xs text-slate-400">user</span>
                )}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-slate-500">Member since</dt>
              <dd className="text-slate-400 text-xs">{new Date(user.created_at).toLocaleDateString()}</dd>
            </div>
          </dl>
        </SectionCard>

        {!me.auth_disabled && (
          <>
            <ChangePasswordCard />
            <SessionsCard />
            <TokensCard />
          </>
        )}
      </div>
    </div>
  );
}
