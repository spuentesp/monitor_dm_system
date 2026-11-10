"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Ban,
  Loader2,
  Search,
  ShieldCheck,
  ShieldOff,
  UserCog,
} from "lucide-react";
import { adminApi, authApi, type AdminUser } from "@/lib/api";

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

export default function AdminPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [banReason, setBanReason] = useState<Record<string, string>>({});

  const { data: me, isLoading: meLoading } = useQuery({
    queryKey: ["auth-me"],
    queryFn: authApi.me,
    retry: false,
  });

  const usersQuery = useQuery({
    queryKey: ["admin-users", search],
    queryFn: () => adminApi.listUsers(search || undefined),
    enabled: !!me?.user.is_admin,
    retry: false,
  });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["admin-users"] });

  const banMutation = useMutation({
    mutationFn: ({ user, reason }: { user: AdminUser; reason?: string }) =>
      adminApi.ban(user.id, reason),
    onSuccess: invalidate,
  });
  const unbanMutation = useMutation({
    mutationFn: (user: AdminUser) => adminApi.unban(user.id),
    onSuccess: invalidate,
  });
  const roleMutation = useMutation({
    mutationFn: ({ user, isAdmin }: { user: AdminUser; isAdmin: boolean }) =>
      adminApi.setRole(user.id, isAdmin),
    onSuccess: invalidate,
  });

  if (meLoading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-amber-400" />
      </div>
    );
  }
  if (!me) {
    router.push("/login");
    return null;
  }
  if (!me.user.is_admin) {
    return (
      <div className="flex-1 flex items-center justify-center p-8">
        <div className="glass rounded-2xl border border-red-500/20 p-8 text-center space-y-2">
          <ShieldOff className="mx-auto h-8 w-8 text-red-400" />
          <p className="text-sm text-slate-300">Operator access required.</p>
        </div>
      </div>
    );
  }

  const users = usersQuery.data?.users ?? [];

  return (
    <div className="flex-1 overflow-y-auto p-6">
      <div className="mx-auto max-w-5xl space-y-5">
        <div className="flex items-center justify-between gap-4">
          <div>
            <h1 className="text-xl font-bold text-slate-100 flex items-center gap-2">
              <UserCog className="h-5 w-5 text-amber-400" /> User administration
            </h1>
            <p className="mt-1 text-sm text-slate-400">
              {usersQuery.data?.total ?? 0} account(s) — ban, unban, and manage operator roles.
            </p>
          </div>
          <div className="relative">
            <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-slate-500" />
            <input
              className="input-cyber pl-8 text-sm"
              placeholder="Search email or username…"
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
                const isSelf = u.id === me.user.id;
                return (
                  <tr key={u.id} className="border-b border-slate-800/60 last:border-0">
                    <td className="px-4 py-3">
                      <div className="font-medium text-slate-100">{u.username}</div>
                      <div className="text-xs text-slate-400">{u.email}</div>
                      {u.banned_reason && (
                        <div className="mt-0.5 text-xs text-red-300/80">“{u.banned_reason}”</div>
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
                      <div className="flex items-center justify-end gap-2">
                        {u.is_banned ? (
                          <button
                            className="btn-ghost text-xs"
                            disabled={isSelf}
                            onClick={() => unbanMutation.mutate(u)}
                          >
                            Unban
                          </button>
                        ) : (
                          <button
                            className="btn-ghost text-xs text-red-300"
                            disabled={isSelf}
                            title={isSelf ? "You cannot ban yourself" : "Ban account"}
                            onClick={() =>
                              banMutation.mutate({ user: u, reason: banReason[u.id] || undefined })
                            }
                          >
                            Ban
                          </button>
                        )}
                        <button
                          className="btn-ghost text-xs"
                          disabled={isSelf}
                          title={isSelf ? "You cannot change your own role" : "Toggle admin"}
                          onClick={() => roleMutation.mutate({ user: u, isAdmin: !u.is_admin })}
                        >
                          {u.is_admin ? "Revoke admin" : "Make admin"}
                        </button>
                      </div>
                      {!u.is_banned && (
                        <input
                          className="input-cyber mt-1 w-full text-xs"
                          placeholder="Ban reason (optional)"
                          value={banReason[u.id] ?? ""}
                          onChange={(e) =>
                            setBanReason((prev) => ({ ...prev, [u.id]: e.target.value }))
                          }
                        />
                      )}
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
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
