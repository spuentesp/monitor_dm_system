"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Ban,
  KeyRound,
  Loader2,
  LogOut,
  Search,
  ShieldCheck,
  ShieldOff,
  UserCog,
} from "lucide-react";
import { adminApi, type AdminUser, type PasswordResetLink } from "@/lib/api";
import { absoluteUrl } from "@/lib/auth-errors";
import { useNotify } from "@/components/NotificationProvider";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { CopyValueDialog } from "@/components/CopyValueDialog";

function StatusBadge({ user }: { user: AdminUser }) {
  if (user.is_banned) {
    return (
      <span className="inline-flex items-center gap-1 rounded-full border border-red-500/30 bg-red-500/10 px-2 py-0.5 text-xs text-red-300">
        <Ban className="h-3 w-3" /> banned
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2 py-0.5 text-xs text-emerald-300">
      active
    </span>
  );
}

type PendingAction =
  | { kind: "ban" | "unban" | "role" | "revokeSessions"; user: AdminUser }
  | null;

export function AdminUsersTab({ meId }: { meId: string }) {
  const queryClient = useQueryClient();
  const { notify } = useNotify();
  const [search, setSearch] = useState("");
  const [pending, setPending] = useState<PendingAction>(null);
  const [banReason, setBanReason] = useState("");
  const [resetLink, setResetLink] = useState<
    (PasswordResetLink & { username: string }) | null
  >(null);

  const usersQuery = useQuery({
    queryKey: ["admin-users", search],
    queryFn: () => adminApi.listUsers(search || undefined),
    retry: false,
  });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["admin-users"] });

  const banMutation = useMutation({
    mutationFn: ({ user, reason }: { user: AdminUser; reason?: string }) =>
      adminApi.ban(user.id, reason),
    onSuccess: () => {
      notify("success", "User banned.");
      setPending(null);
      setBanReason("");
      invalidate();
    },
    onError: (err) => notify("error", (err as Error).message),
  });

  const unbanMutation = useMutation({
    mutationFn: (user: AdminUser) => adminApi.unban(user.id),
    onSuccess: () => {
      notify("success", "User unbanned.");
      setPending(null);
      invalidate();
    },
    onError: (err) => notify("error", (err as Error).message),
  });

  const roleMutation = useMutation({
    mutationFn: ({ user, isAdmin }: { user: AdminUser; isAdmin: boolean }) =>
      adminApi.setRole(user.id, isAdmin),
    onSuccess: (_data, vars) => {
      notify("success", vars.isAdmin ? "Admin role granted." : "Admin role revoked.");
      setPending(null);
      invalidate();
    },
    onError: (err) => notify("error", (err as Error).message),
  });

  const resetMutation = useMutation({
    mutationFn: (user: AdminUser) => adminApi.resetUserPassword(user.id),
    onSuccess: (link, user) => {
      setPending(null);
      setResetLink({ ...link, username: user.username });
    },
    onError: (err) => {
      setPending(null);
      notify("error", (err as Error).message);
    },
  });

  const revokeSessionsMutation = useMutation({
    mutationFn: (user: AdminUser) => adminApi.revokeUserSessions(user.id),
    onSuccess: () => {
      notify("success", "All sessions for that user were revoked.");
      setPending(null);
    },
    onError: (err) => {
      setPending(null);
      notify("error", (err as Error).message);
    },
  });

  const users = usersQuery.data?.users ?? [];
  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h2 className="text-lg font-bold text-slate-100 flex items-center gap-2">
            <UserCog className="h-5 w-5 text-amber-400" /> Users
          </h2>
          <p className="mt-1 text-sm text-slate-400">
            {usersQuery.data?.total ?? 0} account(s) — ban, roles, password resets and
            session revocation.
          </p>
        </div>
        <div className="relative">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-slate-500" />
          <input
            className="input-cyber pl-8 text-sm"
            placeholder="Search email or username…"
            aria-label="Search users"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
      </div>

      <div className="glass rounded-2xl border border-amber-500/10 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-700/60 text-left text-xs uppercase tracking-wide text-slate-500">
              <th className="px-4 py-3">User</th>
              <th className="px-4 py-3">ID</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3">Role</th>
              <th className="px-4 py-3">Verified</th>
              <th className="px-4 py-3">Created</th>
              <th className="px-4 py-3 text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {users.map((u) => {
              const isSelf = u.id === meId;
              return (
                <tr key={u.id} className="border-b border-slate-800/60 last:border-0">
                  <td className="px-4 py-3">
                    <div className="font-medium text-slate-100">{u.username}</div>
                    <div className="text-xs text-slate-400">{u.email}</div>
                    {u.banned_reason && (
                      <div className="mt-0.5 text-xs text-red-300/80">&ldquo;{u.banned_reason}&rdquo;</div>
                    )}
                  </td>
                  <td className="px-4 py-3 font-mono text-xs text-slate-500">{u.id}</td>
                  <td className="px-4 py-3">
                    <StatusBadge user={u} />
                  </td>
                  <td className="px-4 py-3">
                    {u.is_admin ? (
                      <span className="inline-flex items-center gap-1 text-xs text-amber-300">
                        <ShieldCheck className="h-3.5 w-3.5" /> admin
                      </span>
                    ) : (
                      <span className="text-xs text-slate-400">user</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-xs text-slate-400">
                    {u.email_verified ? "yes" : "no"}
                  </td>
                  <td className="px-4 py-3 text-xs text-slate-400">
                    {new Date(u.created_at).toLocaleDateString()}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center justify-end gap-2 flex-wrap">
                      {u.is_banned ? (
                        <button
                          className="btn-ghost text-xs"
                          disabled={isSelf}
                          onClick={() => setPending({ kind: "unban", user: u })}
                        >
                          Unban
                        </button>
                      ) : (
                        <button
                          className="btn-ghost text-xs text-red-300"
                          disabled={isSelf}
                          title={isSelf ? "You cannot ban yourself" : "Ban account"}
                          onClick={() => {
                            setBanReason("");
                            setPending({ kind: "ban", user: u });
                          }}
                        >
                          Ban
                        </button>
                      )}
                      <button
                        className="btn-ghost text-xs"
                        disabled={isSelf}
                        title={isSelf ? "You cannot change your own role" : "Toggle admin"}
                        onClick={() => setPending({ kind: "role", user: u })}
                      >
                        {u.is_admin ? "Revoke admin" : "Make admin"}
                      </button>
                      <button
                        className="btn-ghost text-xs"
                        title="Issue one-time password reset link"
                        onClick={() => resetMutation.mutate(u)}
                        disabled={resetMutation.isPending}
                      >
                        <KeyRound className="inline h-3 w-3 mr-1" />
                        Reset password
                      </button>
                      <button
                        className="btn-ghost text-xs text-red-300"
                        title="Revoke all sessions of this user"
                        onClick={() => setPending({ kind: "revokeSessions", user: u })}
                      >
                        <LogOut className="inline h-3 w-3 mr-1" />
                        Revoke sessions
                      </button>
                    </div>
                  </td>
                </tr>
              );
            })}
            {usersQuery.isLoading && (
              <tr>
                <td colSpan={7} className="px-4 py-8 text-center text-slate-400">
                  <Loader2 className="mx-auto h-5 w-5 animate-spin" />
                </td>
              </tr>
            )}
            {!usersQuery.isLoading && users.length === 0 && (
              <tr>
                <td colSpan={7} className="px-4 py-8 text-center text-slate-400">
                  No users match this search.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {pending?.kind === "ban" && (
        <ConfirmDialog
          title={`Ban ${pending.user.username}`}
          icon={Ban}
          danger
          busy={banMutation.isPending}
          confirmLabel="Ban account"
          message="The account will be blocked from signing in. You can unban at any time."
          onConfirm={() =>
            banMutation.mutate({ user: pending.user, reason: banReason.trim() || undefined })
          }
          onClose={() => setPending(null)}
        >
          <div className="space-y-1.5">
            <label className="text-xs text-slate-500" htmlFor="ban-reason">
              Ban reason (optional, shown to the user)
            </label>
            <input
              id="ban-reason"
              className="input-cyber w-full text-sm"
              placeholder="e.g. spamming other players"
              value={banReason}
              onChange={(e) => setBanReason(e.target.value)}
            />
          </div>
        </ConfirmDialog>
      )}

      {pending?.kind === "unban" && (
        <ConfirmDialog
          title={`Unban ${pending.user.username}`}
          icon={ShieldOff}
          busy={unbanMutation.isPending}
          confirmLabel="Unban"
          message="Restore this account's access?"
          onConfirm={() => unbanMutation.mutate(pending.user)}
          onClose={() => setPending(null)}
        />
      )}

      {pending?.kind === "role" && (
        <ConfirmDialog
          title={pending.user.is_admin ? "Revoke admin" : "Make admin"}
          icon={ShieldCheck}
          busy={roleMutation.isPending}
          confirmLabel={pending.user.is_admin ? "Revoke admin" : "Make admin"}
          message={
            pending.user.is_admin
              ? `Remove operator access from ${pending.user.username}?`
              : `Grant full operator access (users, invites, usage, providers) to ${pending.user.username}?`
          }
          onConfirm={() =>
            roleMutation.mutate({ user: pending.user, isAdmin: !pending.user.is_admin })
          }
          onClose={() => setPending(null)}
        />
      )}

      {pending?.kind === "revokeSessions" && (
        <ConfirmDialog
          title="Revoke sessions"
          icon={LogOut}
          danger
          busy={revokeSessionsMutation.isPending}
          confirmLabel="Revoke all sessions"
          message={`Sign ${pending.user.username} out of every device? Their API tokens keep working.`}
          onConfirm={() => revokeSessionsMutation.mutate(pending.user)}
          onClose={() => setPending(null)}
        />
      )}

      {resetMutation.isPending && (
        <div className="flex items-center gap-2 text-xs text-slate-400">
          <Loader2 className="h-3.5 w-3.5 animate-spin" /> Issuing reset link…
        </div>
      )}

      {resetLink && (
        <CopyValueDialog
          title="Password reset link"
          icon={KeyRound}
          label={`One-time link for ${resetLink.username} — it expires ${new Date(resetLink.expires_at).toLocaleString()}.`}
          value={absoluteUrl(resetLink.url_path)}
          hint="Works without SMTP: hand it to the user over a trusted channel. It resets their password once and signs out all their sessions."
          onClose={() => setResetLink(null)}
        />
      )}
    </div>
  );
}
