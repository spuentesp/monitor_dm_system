"use client";

import { useQuery } from "@tanstack/react-query";
import { Globe2 } from "lucide-react";
import { universesApi } from "@/lib/api";
import { useWorldContext } from "@/lib/world-context";

/**
 * Sidebar world selector (T-077): one persisted "active world" shared across
 * pages. Universes are grouped by multiverse so look-alike names stay
 * distinguishable.
 */
export function WorldPicker({ collapsed }: { collapsed: boolean }) {
  const { universeId, setWorld, clearWorld } = useWorldContext();

  const { data: multiverses = [] } = useQuery({
    queryKey: ["multiverses"],
    queryFn: universesApi.listMultiverses,
    staleTime: 60_000,
  });
  const { data: universes = [] } = useQuery({
    queryKey: ["universes", "all"],
    queryFn: () => universesApi.listUniverses(),
    staleTime: 60_000,
  });

  if (collapsed) {
    return (
      <div
        className="flex justify-center py-1"
        title={
          universeId
            ? `Active world: ${universes.find((u) => u.id === universeId)?.name ?? "selected"}`
            : "No active world"
        }
      >
        <Globe2 className={universeId ? "w-4 h-4 text-cyan-400" : "w-4 h-4 text-slate-700"} />
      </div>
    );
  }

  const mvName = (id: string) => multiverses.find((m) => m.id === id)?.name ?? "Other";
  const grouped = new Map<string, typeof universes>();
  for (const u of universes) {
    const key = u.multiverse_id;
    grouped.set(key, [...(grouped.get(key) ?? []), u]);
  }

  return (
    <div className="px-1 pb-1">
      <label className="flex items-center gap-1.5 px-1.5 pb-1 text-[9px] font-semibold tracking-[0.18em] uppercase text-slate-600">
        <Globe2 className="w-3 h-3 text-cyan-500/70" /> Active world
      </label>
      <select
        value={universeId ?? ""}
        onChange={(e) => {
          const id = e.target.value;
          if (!id) {
            clearWorld();
            return;
          }
          const u = universes.find((x) => x.id === id);
          if (u) {
            setWorld({ multiverseId: u.multiverse_id, universeId: u.id, universeLabel: u.name });
          }
        }}
        className="w-full bg-slate-900/70 border border-white/10 rounded-lg px-2 py-1.5 text-[11px] text-slate-200 focus:outline-none focus:border-cyan-500/50"
        title="Pages default to this world (Play setup, GM Assistant, Worlds tree)"
      >
        <option value="">No world selected</option>
        {[...grouped.entries()].map(([mvId, list]) => (
          <optgroup key={mvId} label={mvName(mvId)}>
            {list.map((u) => (
              <option key={u.id} value={u.id}>
                {u.name}
              </option>
            ))}
          </optgroup>
        ))}
      </select>
    </div>
  );
}
