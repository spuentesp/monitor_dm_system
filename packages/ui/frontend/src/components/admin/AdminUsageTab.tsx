"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Gauge, Loader2, Save } from "lucide-react";
import { adminApi, type UsageEntry } from "@/lib/api";
import { useNotify } from "@/components/NotificationProvider";
import { cn } from "@/lib/utils";

function overCap(u: UsageEntry): boolean {
  if (u.exempt) return false;
  if (u.daily_token_cap !== null && u.tokens > u.daily_token_cap) return true;
  if (u.daily_call_cap !== null && u.calls > u.daily_call_cap) return true;
  return false;
}

function UsageRow({ entry }: { entry: UsageEntry }) {
  const queryClient = useQueryClient();
  const { notify } = useNotify();
  const [tokenCap, setTokenCap] = useState(entry.daily_token_cap === null ? "" : String(entry.daily_token_cap));
  const [callCap, setCallCap] = useState(entry.daily_call_cap === null ? "" : String(entry.daily_call_cap));
  const [exempt, setExempt] = useState(entry.exempt);

  const save = useMutation({
    mutationFn: () => {
      const parseCap = (v: string) => (v.trim() === "" ? null : Math.max(0, Number(v)));
      return adminApi.setUsageLimits(entry.user_id, {
        daily_token_cap: parseCap(tokenCap),
        daily_call_cap: parseCap(callCap),
        exempt,
      });
    },
    onSuccess: () => {
      notify("success", `Limits saved for ${entry.username || entry.email}.`);
      queryClient.invalidateQueries({ queryKey: ["admin-usage"] });
    },
    onError: (err) => notify("error", (err as Error).message),
  });

  const isOver = overCap({ ...entry, daily_token_cap: tokenCap === "" ? null : Number(tokenCap), daily_call_cap: callCap === "" ? null : Number(callCap), exempt });

  return (
    <tr className="border-b border-slate-800/60 last:border-0 align-middle">
      <td className="px-4 py-3">
        <div className="font-medium text-slate-100">{entry.username || "—"}</div>
        <div className="text-xs text-slate-400">{entry.email}</div>
      </td>
      <td className="px-4 py-3 text-right font-mono text-xs">
        <div className="text-slate-200">{entry.tokens.toLocaleString()}</div>
        {entry.daily_token_cap !== null && (
          <div className="text-slate-500">cap {entry.daily_token_cap.toLocaleString()}</div>
        )}
      </td>
      <td className="px-4 py-3 text-right font-mono text-xs">
        <div className="text-slate-200">{entry.calls.toLocaleString()}</div>
        {entry.daily_call_cap !== null && (
          <div className="text-slate-500">cap {entry.daily_call_cap.toLocaleString()}</div>
        )}
      </td>
      <td className="px-4 py-3">
        {isOver ? (
          <span className="inline-flex items-center gap-1 rounded-full border border-red-500/40 bg-red-500/15 px-2 py-0.5 text-xs text-red-300">
            <AlertTriangle className="h-3 w-3" /> over cap
          </span>
        ) : exempt ? (
          <span className="inline-flex rounded-full border border-cyan-500/30 bg-cyan-500/10 px-2 py-0.5 text-xs text-cyan-300">
            exempt
          </span>
        ) : (
          <span className="text-xs text-slate-500">within limits</span>
        )}
      </td>
      <td className="px-4 py-3">
        <div className="flex items-center gap-2">
          <input
            type="number"
            min={0}
            aria-label={`Daily token cap for ${entry.username || entry.email}`}
            className="input-cyber w-24 text-xs"
            placeholder="no cap"
            value={tokenCap}
            onChange={(e) => setTokenCap(e.target.value)}
          />
          <input
            type="number"
            min={0}
            aria-label={`Daily call cap for ${entry.username || entry.email}`}
            className="input-cyber w-20 text-xs"
            placeholder="no cap"
            value={callCap}
            onChange={(e) => setCallCap(e.target.value)}
          />
          <label className="flex items-center gap-1.5 text-xs text-slate-400 whitespace-nowrap">
            <input
              type="checkbox"
              checked={exempt}
              onChange={(e) => setExempt(e.target.checked)}
            />
            exempt
          </label>
          <button
            className="btn-ghost text-xs gap-1"
            onClick={() => save.mutate()}
            disabled={save.isPending}
            aria-label={`Save limits for ${entry.username || entry.email}`}
          >
            {save.isPending ? <Loader2 className="h-3 w-3 animate-spin" /> : <Save className="h-3 w-3" />}
            Save
          </button>
        </div>
      </td>
    </tr>
  );
}

export function AdminUsageTab() {
  const usageQuery = useQuery({
    queryKey: ["admin-usage"],
    queryFn: adminApi.usage,
    retry: false,
  });

  const users = usageQuery.data?.users ?? [];
  const overCount = users.filter(overCap).length;

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h2 className="text-lg font-bold text-slate-100 flex items-center gap-2">
            <Gauge className="h-5 w-5 text-amber-400" /> Usage
          </h2>
          <p className="mt-1 text-sm text-slate-400">
            Tokens and calls today
            {usageQuery.data?.day ? ` (${usageQuery.data.day} UTC)` : ""} against per-user
            daily caps. Caps reset at 00:00 UTC.
          </p>
        </div>
        {overCount > 0 && (
          <span
            className={cn(
              "inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs",
              "border-red-500/40 bg-red-500/15 text-red-300",
            )}
          >
            <AlertTriangle className="h-3.5 w-3.5" /> {overCount} user(s) over cap
          </span>
        )}
      </div>

      <div className="glass rounded-2xl border border-amber-500/10 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-700/60 text-left text-xs uppercase tracking-wide text-slate-500">
              <th className="px-4 py-3">User</th>
              <th className="px-4 py-3 text-right">Tokens today</th>
              <th className="px-4 py-3 text-right">Calls today</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3">Daily limits (tokens / calls)</th>
            </tr>
          </thead>
          <tbody>
            {usageQuery.isLoading && (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center text-slate-400">
                  <Loader2 className="mx-auto h-5 w-5 animate-spin" />
                </td>
              </tr>
            )}
            {!usageQuery.isLoading && users.length === 0 && (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center text-slate-400">
                  No usage recorded today.
                </td>
              </tr>
            )}
            {users.map((u) => (
              <UsageRow key={u.user_id} entry={u} />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
