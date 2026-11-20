"use client";

import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { BookOpen, Globe2, Layers } from "lucide-react";
import { entitiesApi, universesApi } from "@/lib/api";

export function GMSelector({
  universeId,
  systemId,
  onUniverseChange,
  onSystemChange,
  onMultiverseChange,
}: {
  universeId: string | null;
  systemId: string | null;
  onUniverseChange: (id: string | null, label?: string | null) => void;
  onSystemChange: (id: string | null) => void;
  onMultiverseChange?: (id: string | null) => void;
}) {
  const { data: multiverses = [] } = useQuery({ queryKey: ["multiverses"], queryFn: universesApi.listMultiverses });
  const [selectedMv, setSelectedMv] = useState<string | null>(null);

  const { data: universes = [] } = useQuery({
    queryKey: ["universes", selectedMv],
    queryFn: () => universesApi.listUniverses(selectedMv ?? undefined),
    enabled: true,
  });

  const { data: systems = [] } = useQuery({
    queryKey: ["systems"],
    queryFn: entitiesApi.listSystems,
  });

  // Keep the multiverse callback in sync (the notebook binds ingestion to it)
  useEffect(() => {
    const owner = universes.find((u) => u.id === universeId)?.multiverse_id ?? selectedMv;
    onMultiverseChange?.(owner ?? null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedMv, universeId, universes.length]);

  return (
    <div className="flex items-center gap-3 flex-wrap">
      <div className="flex items-center gap-1.5">
        <Layers className="w-3.5 h-3.5 text-purple-400 flex-shrink-0" />
        <select
          value={selectedMv ?? ""}
          onChange={(e) => { setSelectedMv(e.target.value || null); onUniverseChange(null); }}
          className="input-cyber py-1 text-xs min-w-[120px] max-xl:min-h-11"
        >
          <option value="">All multiverses</option>
          {multiverses.map((mv) => <option key={mv.id} value={mv.id}>{mv.name}</option>)}
        </select>
      </div>
      <div className="flex items-center gap-1.5">
        <Globe2 className="w-3.5 h-3.5 text-cyan-400 flex-shrink-0" />
        <select
          value={universeId ?? ""}
          onChange={(e) => {
            const id = e.target.value || null;
            onUniverseChange(id, universes.find((u) => u.id === id)?.name ?? null);
          }}
          className="input-cyber py-1 text-xs min-w-[140px] max-xl:min-h-11"
        >
          <option value="">Select universe…</option>
          {universes.map((uv) => <option key={uv.id} value={uv.id}>{uv.name}</option>)}
        </select>
      </div>
      {systems.length > 0 && (
        <div className="flex items-center gap-1.5">
          <BookOpen className="w-3.5 h-3.5 text-emerald-400 flex-shrink-0" />
          <select
            value={systemId ?? ""}
            onChange={(e) => onSystemChange(e.target.value || null)}
            className="input-cyber py-1 text-xs min-w-[140px] max-xl:min-h-11"
          >
            <option value="">No system selected</option>
            {systems.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
        </div>
      )}
    </div>
  );
}
