"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link2, Loader2, Plus, Ticket, XCircle } from "lucide-react";
import { adminApi, type Invite, type InviteCreated } from "@/lib/api";
import { absoluteUrl } from "@/lib/auth-errors";
import { useNotify } from "@/components/NotificationProvider";
import { CopyValueDialog } from "@/components/CopyValueDialog";
import { ConfirmDialog } from "@/components/ConfirmDialog";

function inviteStatus(invite: Invite): { label: string; className: string } {
  if (invite.revoked_at) return { label: "revoked", className: "border-slate-600 bg-white/5 text-slate-400" };
  if (invite.used_at) return { label: "used", className: "border-cyan-500/30 bg-cyan-500/10 text-cyan-300" };
  if (new Date(invite.expires_at).getTime() < Date.now()) {
    return { label: "expired", className: "border-amber-500/30 bg-amber-500/10 text-amber-300" };
  }
  return { label: "active", className: "border-emerald-500/30 bg-emerald-500/10 text-emerald-300" };
}

export function AdminInvitesTab() {
  const queryClient = useQueryClient();
  const { notify } = useNotify();
  const [email, setEmail] = useState("");
  const [hours, setHours] = useState("168");
  const [created, setCreated] = useState<InviteCreated | null>(null);
  const [revokeTarget, setRevokeTarget] = useState<Invite | null>(null);

  const invitesQuery = useQuery({
    queryKey: ["admin-invites"],
    queryFn: adminApi.listInvites,
    retry: false,
  });

  const createMutation = useMutation({
    mutationFn: () => {
      const hoursNum = Number(hours);
      const expires = Number.isFinite(hoursNum) && hoursNum > 0 ? hoursNum : 168;
      return adminApi.createInvite(email.trim() || undefined, expires);
    },
    onSuccess: (invite) => {
      setCreated(invite);
      setEmail("");
      queryClient.invalidateQueries({ queryKey: ["admin-invites"] });
    },
    onError: (err) => notify("error", (err as Error).message),
  });

  const revokeMutation = useMutation({
    mutationFn: (invite: Invite) => adminApi.revokeInvite(invite.id),
    onSuccess: () => {
      notify("success", "Invite revoked.");
      setRevokeTarget(null);
      queryClient.invalidateQueries({ queryKey: ["admin-invites"] });
    },
    onError: (err) => {
      setRevokeTarget(null);
      notify("error", (err as Error).message);
    },
  });

  const invites = invitesQuery.data?.invites ?? [];

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-lg font-bold text-slate-100 flex items-center gap-2">
          <Ticket className="h-5 w-5 text-amber-400" /> Invites
        </h2>
        <p className="mt-1 text-sm text-slate-400">
          Invite links let new users sign up while sign-ups are invite-only. Each link
          works exactly once.
        </p>
      </div>

      <form
        className="glass rounded-2xl border border-amber-500/10 p-4 flex flex-wrap items-end gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          createMutation.mutate();
        }}
      >
        <div className="space-y-1.5 min-w-56 flex-1">
          <label className="text-xs text-slate-500" htmlFor="invite-email">
            Restrict to email (optional)
          </label>
          <input
            id="invite-email"
            type="email"
            className="input-cyber w-full text-sm"
            placeholder="anyone with the link"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </div>
        <div className="space-y-1.5 w-40">
          <label className="text-xs text-slate-500" htmlFor="invite-hours">
            Expires in (hours)
          </label>
          <input
            id="invite-hours"
            type="number"
            min={1}
            className="input-cyber w-full text-sm"
            value={hours}
            onChange={(e) => setHours(e.target.value)}
          />
        </div>
        <button type="submit" className="btn-cyber text-xs gap-1.5" disabled={createMutation.isPending}>
          {createMutation.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Plus className="h-3.5 w-3.5" />}
          Create invite
        </button>
      </form>

      <div className="glass rounded-2xl border border-amber-500/10 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-700/60 text-left text-xs uppercase tracking-wide text-slate-500">
              <th className="px-4 py-3">Email</th>
              <th className="px-4 py-3">Created</th>
              <th className="px-4 py-3">Expires</th>
              <th className="px-4 py-3">Used</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3 text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {invitesQuery.isLoading && (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-slate-400">
                  <Loader2 className="mx-auto h-5 w-5 animate-spin" />
                </td>
              </tr>
            )}
            {!invitesQuery.isLoading && invites.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-slate-400">
                  No invites yet — create one above.
                </td>
              </tr>
            )}
            {invites.map((inv) => {
              const status = inviteStatus(inv);
              const revocable = !inv.revoked_at && !inv.used_at;
              return (
                <tr key={inv.id} className="border-b border-slate-800/60 last:border-0">
                  <td className="px-4 py-3">
                    {inv.email ? (
                      <span className="text-slate-100">{inv.email}</span>
                    ) : (
                      <span className="text-slate-500">anyone with the link</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-xs text-slate-400">
                    {new Date(inv.created_at).toLocaleDateString()}
                  </td>
                  <td className="px-4 py-3 text-xs text-slate-400">
                    {new Date(inv.expires_at).toLocaleString()}
                  </td>
                  <td className="px-4 py-3 text-xs text-slate-400">
                    {inv.used_at ? new Date(inv.used_at).toLocaleDateString() : "—"}
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={`inline-flex rounded-full border px-2 py-0.5 text-xs ${status.className}`}
                    >
                      {status.label}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right">
                    <button
                      className="btn-ghost text-xs text-red-300"
                      disabled={!revocable || revokeMutation.isPending}
                      title={revocable ? "Revoke invite" : "Already used, expired or revoked"}
                      onClick={() => setRevokeTarget(inv)}
                    >
                      Revoke
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {created && (
        <CopyValueDialog
          title="Invite created"
          icon={Link2}
          label={`Invite link${created.expires_at ? ` — expires ${new Date(created.expires_at).toLocaleString()}` : ""} — send it to the person you invited.`}
          value={absoluteUrl(created.url_path)}
          hint="The link opens the sign-up form with the code already filled in. It stops working after the first successful sign-up or when you revoke it."
          onClose={() => setCreated(null)}
        />
      )}

      {revokeTarget && (
        <ConfirmDialog
          title="Revoke invite"
          icon={XCircle}
          danger
          busy={revokeMutation.isPending}
          confirmLabel="Revoke invite"
          message={
            revokeTarget.email
              ? `Revoke the invite for ${revokeTarget.email}? The link will stop working immediately.`
              : "Revoke this invite? The link will stop working immediately."
          }
          onConfirm={() => revokeMutation.mutate(revokeTarget)}
          onClose={() => setRevokeTarget(null)}
        />
      )}
    </div>
  );
}
