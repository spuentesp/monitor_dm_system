"use client";

import { useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { type Node, type Edge } from "@xyflow/react";
import { AnimatePresence, motion } from "framer-motion";
import { ChevronLeft, ChevronRight, Filter, Globe2, Layers, Link2, Loader2, MapPin, Network, RefreshCw, Search, Shield, Sparkles, User, WifiOff, X } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { cn } from "@/lib/utils";
import { entitiesApi, graphApi, universesApi } from "@/lib/api";
import { InspectorPanel } from "./InspectorPanel";
import { GraphLegend } from "./GraphLegend";
import { GraphCanvas } from "./GraphCanvas";
import type { GraphNodeData, WorldGraphFilter } from "@/lib/types";

export function GraphTab() {
  const qc = useQueryClient();
  const [selectedNode, setSelectedNode] = useState<Node<GraphNodeData> | null>(null);
  const [panelOpen, setPanelOpen] = useState(true);
  const [filtersOpen, setFiltersOpen] = useState(false);

  // ── Filter state ──────────────────────────────────────────
  const [filterMvId, setFilterMvId] = useState<string | null>(null);
  const [filterUnivId, setFilterUnivId] = useState<string | null>(null);
  const [filterEntityTypes, setFilterEntityTypes] = useState<Set<string>>(new Set());
  const [relatedTo, setRelatedTo] = useState<string | null>(null);
  const [relatedToLabel, setRelatedToLabel] = useState<string | null>(null);
  const [entitySearch, setEntitySearch] = useState("");

  // ── Load multiverses / universes for dropdowns ────────────
  const { data: multiverses = [] } = useQuery({
    queryKey: ["multiverses"],
    queryFn: universesApi.listMultiverses,
  });

  // Auto-select first multiverse when data loads
  useEffect(() => {
    if (!filterMvId && multiverses.length > 0) {
      setFilterMvId(multiverses[0].id);
    }
  }, [multiverses, filterMvId]);

  const { data: allUniverses = [] } = useQuery({
    queryKey: ["universes", filterMvId],
    queryFn: () => universesApi.listUniverses(filterMvId ?? undefined),
  });

  // ── Build the filter object ───────────────────────────────
  const graphFilter: WorldGraphFilter | undefined = useMemo(() => {
    const f: WorldGraphFilter = {};
    if (filterMvId) f.multiverse_id = filterMvId;
    if (filterUnivId) f.universe_id = filterUnivId;
    if (filterEntityTypes.size > 0) f.entity_types = [...filterEntityTypes];
    if (relatedTo) f.related_to = relatedTo;
    if (!f.multiverse_id && !f.universe_id && !f.entity_types && !f.related_to) return undefined;
    return f;
  }, [filterMvId, filterUnivId, filterEntityTypes, relatedTo]);

  // ── Entity search for "related to" ────────────────────────
  const { data: entitySearchResults = [] } = useQuery({
    queryKey: ["entitySearch", entitySearch],
    queryFn: () => entitiesApi.search(entitySearch, 10),
    enabled: entitySearch.length >= 2,
    staleTime: 10_000,
  });

  // ── Graph query ───────────────────────────────────────────
  const { data, isLoading, error } = useQuery({
    queryKey: ["worldGraph", graphFilter],
    queryFn: () => graphApi.getWorldGraph(graphFilter),
    staleTime: 30_000,
    retry: 1,
  });

  const graphNodes = (data?.nodes ?? []) as Node<GraphNodeData>[];
  const graphEdges = (data?.edges ?? []) as Edge[];
  const dbError = data?.error ?? (error ? String(error) : null);
  const availableEntityTypes = data?.entity_types ?? [];

  const hasFilters = filterMvId || filterUnivId || filterEntityTypes.size > 0 || relatedTo;

  const clearFilters = () => {
    setFilterMvId(null);
    setFilterUnivId(null);
    setFilterEntityTypes(new Set());
    setRelatedTo(null);
    setRelatedToLabel(null);
    setEntitySearch("");
  };

  const toggleEntityType = (t: string) => {
    setFilterEntityTypes((prev) => {
      const next = new Set(prev);
      if (next.has(t)) next.delete(t);
      else next.add(t);
      return next;
    });
  };

  // ENTITY_TYPE labels for chips
  const ENTITY_TYPE_CHIP: Record<string, { icon: React.ElementType; color: string }> = {
    character: { icon: User, color: "text-cyan-300 border-cyan-500/25 bg-cyan-500/8" },
    location: { icon: MapPin, color: "text-amber-400 border-amber-500/25 bg-amber-500/8" },
    faction: { icon: Shield, color: "text-emerald-400 border-emerald-500/25 bg-emerald-500/8" },
    organization: { icon: Shield, color: "text-emerald-400 border-emerald-500/25 bg-emerald-500/8" },
    concept: { icon: Sparkles, color: "text-pink-400 border-pink-500/25 bg-pink-500/8" },
    object: { icon: Sparkles, color: "text-pink-400 border-pink-500/25 bg-pink-500/8" },
    creature: { icon: User, color: "text-cyan-300 border-cyan-500/25 bg-cyan-500/8" },
    npc: { icon: User, color: "text-cyan-300 border-cyan-500/25 bg-cyan-500/8" },
  };

  return (
    <div className="flex flex-col h-full">
      {/* Toolbar */}
      <div className="flex items-center gap-3 px-4 h-11 border-b border-white/5 glass-dark flex-shrink-0">
        {isLoading ? (
          <span className="flex items-center gap-1.5 text-xs text-slate-600">
            <Loader2 className="w-3 h-3 animate-spin" /> loading…
          </span>
        ) : dbError ? (
          <span className="flex items-center gap-1.5 text-xs text-red-400/80">
            <WifiOff className="w-3 h-3" /> DB offline
          </span>
        ) : (
          <span className="text-xs text-slate-600">
            {graphNodes.length} nodes · {graphEdges.length} edges
          </span>
        )}

        <div className="flex-1" />

        <button
          onClick={() => setFiltersOpen((v) => !v)}
          className={cn(
            "flex items-center gap-1.5 text-xs py-1.5 px-3 rounded-lg border transition-all",
            hasFilters
              ? "bg-cyan-500/10 border-cyan-500/25 text-cyan-300"
              : filtersOpen
                ? "bg-white/5 border-white/10 text-slate-300"
                : "border-transparent text-slate-500 hover:text-slate-300",
          )}
        >
          <Filter className="w-3.5 h-3.5" />
          Filters
          {hasFilters && (
            <span className="text-[9px] bg-cyan-500/20 rounded-full w-4 h-4 flex items-center justify-center">
              {(filterMvId ? 1 : 0) + (filterUnivId ? 1 : 0) + (filterEntityTypes.size > 0 ? 1 : 0) + (relatedTo ? 1 : 0)}
            </span>
          )}
        </button>

        {hasFilters && (
          <button onClick={clearFilters} className="text-xs text-slate-600 hover:text-slate-300 transition-colors" title="Clear all filters">
            <X className="w-3.5 h-3.5" />
          </button>
        )}

        <button
          onClick={() => qc.invalidateQueries({ queryKey: ["worldGraph"] })}
          className="btn-ghost py-1.5 px-2"
          title="Refresh"
        >
          <RefreshCw className={cn("w-3.5 h-3.5", isLoading && "animate-spin")} />
        </button>

        <button
          onClick={() => setPanelOpen((p) => !p)}
          className="btn-ghost py-1.5 px-2"
          title={panelOpen ? "Hide inspector" : "Show inspector"}
        >
          {panelOpen ? <ChevronRight className="w-4 h-4" /> : <ChevronLeft className="w-4 h-4" />}
        </button>
      </div>

      {/* Filter bar */}
      <AnimatePresence>
        {filtersOpen && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.15 }}
            className="overflow-hidden border-b border-white/5"
          >
            <div className="px-4 py-3 space-y-3 glass-dark">
              {/* Row 1: Setting + Universe dropdowns */}
              <div className="flex items-center gap-3 flex-wrap">
                <div className="flex items-center gap-2">
                  <label className="text-[10px] text-slate-600 uppercase tracking-wider font-medium w-12">Setting</label>
                  <select
                    value={filterMvId ?? ""}
                    onChange={(e) => {
                      setFilterMvId(e.target.value || null);
                      setFilterUnivId(null);
                    }}
                    className="bg-slate-900/60 border border-white/10 rounded-lg px-3 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-cyan-500/50 min-w-[180px]"
                  >
                    <option value="">All settings</option>
                    {multiverses.map((mv) => (
                      <option key={mv.id} value={mv.id}>{mv.name}</option>
                    ))}
                  </select>
                </div>

                <div className="flex items-center gap-2">
                  <label className="text-[10px] text-slate-600 uppercase tracking-wider font-medium w-14">Universe</label>
                  <select
                    value={filterUnivId ?? ""}
                    onChange={(e) => setFilterUnivId(e.target.value || null)}
                    className="bg-slate-900/60 border border-white/10 rounded-lg px-3 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-cyan-500/50 min-w-[180px]"
                    disabled={allUniverses.length === 0}
                  >
                    <option value="">All universes</option>
                    {allUniverses.map((u) => (
                      <option key={u.id} value={u.id}>{u.name}</option>
                    ))}
                  </select>
                </div>
              </div>

              {/* Row 2: Entity type toggles */}
              <div className="flex items-center gap-2 flex-wrap">
                <label className="text-[10px] text-slate-600 uppercase tracking-wider font-medium w-12">Types</label>
                {availableEntityTypes.map((t) => {
                  const chip = ENTITY_TYPE_CHIP[t] ?? { icon: Sparkles, color: "text-slate-400 border-white/10 bg-white/4" };
                  const Icon = chip.icon;
                  const active = filterEntityTypes.has(t);
                  return (
                    <button
                      key={t}
                      onClick={() => toggleEntityType(t)}
                      className={cn(
                        "flex items-center gap-1.5 px-2.5 py-1 rounded-lg border text-[11px] font-medium transition-all capitalize",
                        active ? chip.color : "border-white/5 text-slate-600 hover:text-slate-300 hover:border-white/10",
                      )}
                    >
                      <Icon className="w-3 h-3" />
                      {t}
                    </button>
                  );
                })}
                {availableEntityTypes.length === 0 && (
                  <span className="text-[11px] text-slate-700 italic">Load graph to see types</span>
                )}
              </div>

              {/* Row 3: Related-to search */}
              <div className="flex items-center gap-2 flex-wrap">
                <label className="text-[10px] text-slate-600 uppercase tracking-wider font-medium w-12 flex-shrink-0">
                  <Link2 className="w-3 h-3 inline mr-1" />Focus
                </label>

                {relatedTo ? (
                  <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-purple-500/10 border border-purple-500/25 text-xs text-purple-300">
                    <Link2 className="w-3 h-3" />
                    {relatedToLabel ?? relatedTo.slice(0, 8)}
                    <button onClick={() => { setRelatedTo(null); setRelatedToLabel(null); }} className="text-purple-500 hover:text-purple-300 ml-1">
                      <X className="w-3 h-3" />
                    </button>
                  </div>
                ) : (
                  <div className="relative flex-1 max-w-[320px]">
                    <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3 h-3 text-slate-600" />
                    <input
                      value={entitySearch}
                      onChange={(e) => setEntitySearch(e.target.value)}
                      placeholder="Search an entity to see its connections…" aria-label="Search entities by name"
                      className="w-full bg-slate-900/60 border border-white/10 rounded-lg pl-7 pr-3 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-cyan-500/50"
                    />
                    {entitySearch.length >= 2 && entitySearchResults.length > 0 && (
                      <div className="absolute top-full mt-1 left-0 right-0 glass-dark rounded-lg border border-white/10 overflow-hidden z-20 max-h-52 overflow-y-auto">
                        {entitySearchResults.map((e) => (
                          <button
                            key={e.id}
                            onClick={() => {
                              setRelatedTo(e.id);
                              setRelatedToLabel(e.name);
                              setEntitySearch("");
                            }}
                            className="w-full text-left flex items-center gap-2 px-3 py-2 text-xs hover:bg-white/5 transition-colors"
                          >
                            <span className="text-slate-200 font-medium">{e.name}</span>
                            <span className="text-[10px] text-slate-600 capitalize">{e.type}</span>
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                )}
                <span className="text-[10px] text-slate-700 italic">Show only directly connected entities</span>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Active filter summary (when bar is collapsed but filters are on) */}
      {hasFilters && !filtersOpen && (
        <div className="flex items-center gap-2 px-4 py-1.5 border-b border-white/5 glass-dark flex-shrink-0 flex-wrap">
          <span className="text-[10px] text-slate-600">Filtered:</span>
          {filterMvId && (
            <span className="tag-dim text-[10px] flex items-center gap-1">
              <Layers className="w-2.5 h-2.5" />
              {multiverses.find((mv) => mv.id === filterMvId)?.name ?? "Setting"}
              <button onClick={() => { setFilterMvId(null); setFilterUnivId(null); }}><X className="w-2.5 h-2.5" /></button>
            </span>
          )}
          {filterUnivId && (
            <span className="tag-dim text-[10px] flex items-center gap-1">
              <Globe2 className="w-2.5 h-2.5" />
              {allUniverses.find((u) => u.id === filterUnivId)?.name ?? "Universe"}
              <button onClick={() => setFilterUnivId(null)}><X className="w-2.5 h-2.5" /></button>
            </span>
          )}
          {filterEntityTypes.size > 0 && (
            <span className="tag-dim text-[10px] flex items-center gap-1">
              {[...filterEntityTypes].join(", ")}
              <button onClick={() => setFilterEntityTypes(new Set())}><X className="w-2.5 h-2.5" /></button>
            </span>
          )}
          {relatedTo && (
            <span className="tag-dim text-[10px] flex items-center gap-1 text-purple-300">
              <Link2 className="w-2.5 h-2.5" />
              {relatedToLabel ?? relatedTo.slice(0, 8)}
              <button onClick={() => { setRelatedTo(null); setRelatedToLabel(null); }}><X className="w-2.5 h-2.5" /></button>
            </span>
          )}
        </div>
      )}

      {/* Canvas + Inspector */}
      <div className="flex-1 flex overflow-hidden">
        <div className="flex-1 relative">
          {isLoading ? (
            <div className="flex items-center justify-center h-full text-slate-700 gap-2">
              <Loader2 className="w-5 h-5 animate-spin" />
              <span className="text-sm">Loading world graph…</span>
            </div>
          ) : dbError && graphNodes.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full gap-3 text-center px-8">
              <WifiOff className="w-10 h-10 text-slate-800" />
              <p className="text-sm text-slate-500">Database offline</p>
              <p className="text-xs text-slate-700 max-w-xs leading-relaxed">
                Start Neo4j to populate the graph with your world data.
              </p>
            </div>
          ) : graphNodes.length === 0 && hasFilters ? (
            <div className="flex flex-col items-center justify-center h-full gap-3 text-center px-8">
              <Filter className="w-10 h-10 text-slate-800" />
              <p className="text-sm text-slate-500">No results match your filters</p>
              <button onClick={clearFilters} className="btn-cyber text-xs">
                <X className="w-3.5 h-3.5" /> Clear filters
              </button>
            </div>
          ) : graphNodes.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full gap-3 text-center px-8">
              <Network className="w-10 h-10 text-slate-800" />
              <p className="text-sm text-slate-500">No world data yet</p>
              <p className="text-xs text-slate-700 max-w-xs leading-relaxed">
                Create a multiverse and universe in the Worlds tab, then ingest source material to populate the graph.
              </p>
            </div>
          ) : (
            <GraphCanvas
              initialNodes={graphNodes}
              initialEdges={graphEdges}
              onNodeSelect={(n) => {
                setSelectedNode(n);
                if (n) setPanelOpen(true);
              }}
            />
          )}

          {graphNodes.length > 0 && (
            <div className="absolute top-3 left-3 z-10">
              <GraphLegend />
            </div>
          )}
        </div>

        <AnimatePresence>
          {panelOpen && (
            <motion.div
              initial={{ width: 0, opacity: 0 }}
              animate={{ width: 300, opacity: 1 }}
              exit={{ width: 0, opacity: 0 }}
              transition={{ type: "spring", stiffness: 320, damping: 32 }}
              className="flex-shrink-0 border-l border-white/5 glass-dark flex flex-col overflow-hidden"
            >
              <div className="flex items-center justify-between px-4 py-3 border-b border-white/5 flex-shrink-0">
                <span className="text-xs font-semibold text-slate-400 tracking-wide">Inspector</span>
                <button onClick={() => setPanelOpen(false)} className="text-slate-600 hover:text-slate-300 transition-colors">
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>
              <InspectorPanel
                node={selectedNode}
                onFocusEntity={(id, label) => {
                  setRelatedTo(id);
                  setRelatedToLabel(label);
                  setFiltersOpen(true);
                }}
              />
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
//  HIERARCHY TAB (from /universes)
// ═══════════════════════════════════════════════════════════════

