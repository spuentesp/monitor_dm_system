"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { modesApi } from "@/lib/api";
import type { ActiveMode, ModeConfig } from "@/lib/types";

/**
 * Compact global mode switcher (SYS modes API — autonomous_gm /
 * world_architect / gm_assistant). Lives in the sidebar footer so the
 * active mode is visible and switchable from every page.
 */
export function ModeSwitcher({ collapsed }: { collapsed: boolean }) {
  const qc = useQueryClient();

  const modesQ = useQuery({
    queryKey: ["modes"],
    queryFn: () => modesApi.list(),
    staleTime: 5 * 60_000,
  });
  const activeQ = useQuery({
    queryKey: ["modes", "active"],
    queryFn: () => modesApi.getActive(),
  });

  const setActive = useMutation({
    mutationFn: (mode_id: string) => modesApi.setActive({ mode_id }),
    onSuccess: (data: ActiveMode) => {
      qc.setQueryData(["modes", "active"], data);
    },
  });

  if (collapsed || modesQ.isError || activeQ.isError) return null;

  const modes: ModeConfig[] = modesQ.data ?? [];
  const active = activeQ.data?.mode_id ?? "";

  return (
    <div className="px-2.5 pb-1">
      <label className="block text-[10px] uppercase tracking-wide text-slate-600 mb-1">
        Mode
      </label>
      <select
        value={active}
        disabled={setActive.isPending || modes.length === 0}
        onChange={(e) => setActive.mutate(e.target.value)}
        className="w-full bg-zinc-900 border border-zinc-800 rounded-md px-2 py-1 text-xs text-slate-300 focus:outline-none focus:border-cyan-600 disabled:opacity-50"
        title="Active system mode"
      >
        {modes.map((m) => (
          <option key={m.id} value={m.id}>
            {m.label}
          </option>
        ))}
      </select>
    </div>
  );
}
