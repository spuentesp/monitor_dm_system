"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  GitBranch,
  Landmark,
  Loader2,
  Network,
  Sparkles,
  Zap,
} from "lucide-react";
import { universesApi } from "@/lib/api";
import { useWorldContext } from "@/lib/world-context";
import { cn } from "@/lib/utils";
import { FactsTab } from "./FactsTab";
import { AxiomsTab } from "./AxiomsTab";
import { EventsTab } from "./EventsTab";
import { RelationshipsTab } from "./RelationshipsTab";

// ─── /forge/ontology (F2-2 phase 6) ───────────────────────────
// Management UI for the per-universe ontology: facts, axioms, temporal
// events, and relationships. Entities live in /forge/worlds; templates are
// owned by F3-2.

const TABS = [
  { id: "facts", label: "Facts", icon: Sparkles },
  { id: "axioms", label: "Axioms", icon: Landmark },
  { id: "events", label: "Events", icon: Zap },
  { id: "relationships", label: "Relationships", icon: GitBranch },
] as const;

type OntologyTab = (typeof TABS)[number]["id"];

export default function OntologyPage() {
  const world = useWorldContext();
  const [tab, setTab] = useState<OntologyTab>("facts");
  const [picked, setPicked] = useState<string | null>(null);

  const universesQ = useQuery({
    queryKey: ["universes", "all"],
    queryFn: () => universesApi.listUniverses(),
  });
  const universes = universesQ.data ?? [];

  // Explicit pick wins; otherwise the WorldContext selection (when it is a
  // real universe) or the first universe in the list.
  const universeId =
    picked ??
    (world.universeId && universes.some((u) => u.id === world.universeId)
      ? world.universeId
      : (universes[0]?.id ?? null));

  return (
    <div className="flex flex-col h-full">
      {/* Header: title + universe picker + tabs */}
      <div className="flex items-center gap-4 px-6 py-3 border-b border-white/5 glass-dark flex-shrink-0">
        <Network className="w-5 h-5 text-cyan-400 flex-shrink-0" />
        <h1 className="text-sm font-bold text-slate-200">Ontology</h1>
        <div className="h-5 w-px bg-white/10" />
        <div className="flex items-center gap-1">
          {TABS.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              onClick={() => setTab(id)}
              className={cn(
                "flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium transition-all",
                tab === id
                  ? "bg-cyan-500/10 text-cyan-300 border border-cyan-500/25"
                  : "text-slate-500 hover:text-slate-300 border border-transparent",
              )}
            >
              <Icon className="w-3.5 h-3.5" />
              {label}
            </button>
          ))}
        </div>
        <div className="flex-1" />
        <div>
          <label className="block text-[10px] text-slate-600 mb-0.5">Universe</label>
          {universesQ.isLoading ? (
            <span className="flex items-center gap-1.5 text-xs text-slate-600">
              <Loader2 className="w-3 h-3 animate-spin" /> loading…
            </span>
          ) : (
            <select
              aria-label="Universe"
              className="input-cyber py-1 text-xs min-w-[180px]"
              value={universeId ?? ""}
              onChange={(e) => setPicked(e.target.value || null)}
            >
              {universes.length === 0 && <option value="">— no universes —</option>}
              {universes.map((u) => (
                <option key={u.id} value={u.id}>
                  {u.name}
                </option>
              ))}
            </select>
          )}
        </div>
      </div>

      {/* Tab content */}
      <div className="flex-1 overflow-hidden">
        {!universeId && !universesQ.isLoading ? (
          <div className="flex flex-col items-center justify-center h-full gap-3 text-slate-500">
            <Network className="w-10 h-10 opacity-30" />
            <p className="text-sm">Create a universe first — ontology entries live inside one.</p>
          </div>
        ) : universeId ? (
          <>
            {tab === "facts" && <FactsTab universeId={universeId} />}
            {tab === "axioms" && <AxiomsTab universeId={universeId} />}
            {tab === "events" && <EventsTab universeId={universeId} />}
            {tab === "relationships" && <RelationshipsTab universeId={universeId} />}
          </>
        ) : null}
      </div>
    </div>
  );
}
