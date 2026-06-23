"use client";

import { Suspense, memo, useCallback, useEffect, useState, useMemo } from "react";
import { useSearchParams } from "next/navigation";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  BackgroundVariant,
  Handle,
  Position,
  type Node,
  type Edge,
  type NodeProps,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { AnimatePresence, motion } from "framer-motion";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Brain,
  ChevronLeft,
  ChevronRight,
  Edit2,
  Filter,
  Globe2,
  Layers,
  Link2,
  Loader2,
  MapPin,
  MemoryStick,
  Network,
  Plus,
  RefreshCw,
  Search,
  Shield,
  Sparkles,
  Tag,
  Trash2,
  User,
  Users,
  WifiOff,
  X,
  Zap,
} from "lucide-react";
import { entitiesApi, graphApi, universesApi } from "@/lib/api";
import type {
  GraphNodeData,
  GraphNodeKind,
  GraphNode,
  GraphEdge,
  Multiverse,
  NPC,
  NPCDetail,
  Universe,
  WorldGraphFilter,
} from "@/lib/types";
import { cn, formatRelativeTime, truncate } from "@/lib/utils";
import { UniverseTree } from "@/components/worlds/UniverseTree";
import { useWorldContext } from "@/lib/world-context";

// ─── Tab definitions ───────────────────────────────────────────

const WORLD_TABS = [
  { id: "graph",     label: "World Graph",     icon: Network },
  { id: "hierarchy", label: "Tree & Stories",  icon: Globe2 },
  { id: "entities",  label: "Entities",        icon: Users },
] as const;

type WorldTab = (typeof WORLD_TABS)[number]["id"];

// ═══════════════════════════════════════════════════════════════
//  GRAPH TAB (from /architect)
// ═══════════════════════════════════════════════════════════════

const KIND_CONFIG: Record<
  GraphNodeKind,
  {
    border: string;
    bg: string;
    icon: React.ElementType;
    iconColor: string;
    tagClass: string;
    label: string;
  }
> = {
  multiverse: {
    border: "border-purple-500/40",
    bg: "bg-purple-500/8",
    icon: Layers,
    iconColor: "text-purple-400",
    tagClass: "tag-purple",
    label: "Multiverse",
  },
  universe: {
    border: "border-cyan-500/40",
    bg: "bg-cyan-500/8",
    icon: Globe2,
    iconColor: "text-cyan-400",
    tagClass: "tag-cyan",
    label: "Universe",
  },
  character: {
    border: "border-cyan-500/25",
    bg: "bg-cyan-500/5",
    icon: User,
    iconColor: "text-cyan-300",
    tagClass: "tag-cyan",
    label: "Character",
  },
  location: {
    border: "border-amber-500/30",
    bg: "bg-amber-500/8",
    icon: MapPin,
    iconColor: "text-amber-400",
    tagClass: "tag-amber",
    label: "Location",
  },
  faction: {
    border: "border-emerald-500/30",
    bg: "bg-emerald-500/8",
    icon: Shield,
    iconColor: "text-emerald-400",
    tagClass: "tag-emerald",
    label: "Faction",
  },
  concept: {
    border: "border-pink-500/25",
    bg: "bg-pink-500/5",
    icon: Sparkles,
    iconColor: "text-pink-400",
    tagClass: "tag-red",
    label: "Concept",
  },
  axiom: {
    border: "border-indigo-500/25",
    bg: "bg-indigo-500/5",
    icon: Zap,
    iconColor: "text-indigo-400",
    tagClass: "tag-purple",
    label: "Axiom",
  },
  lore: {
    border: "border-amber-500/20",
    bg: "bg-amber-500/5",
    icon: Brain,
    iconColor: "text-amber-300",
    tagClass: "tag-amber",
    label: "Lore",
  },
  rule: {
    border: "border-slate-500/25",
    bg: "bg-slate-500/5",
    icon: Shield,
    iconColor: "text-slate-400",
    tagClass: "tag-dim",
    label: "Rule",
  },
  pack: {
    border: "border-teal-500/25",
    bg: "bg-teal-500/5",
    icon: Layers,
    iconColor: "text-teal-400",
    tagClass: "tag-cyan",
    label: "Pack",
  },
};

const WorldNode = memo(({ data, selected }: NodeProps) => {
  const d = data as GraphNodeData;
  const cfg = KIND_CONFIG[d.kind];
  const Icon = cfg.icon;
  const isLarge = d.kind === "multiverse" || d.kind === "universe";

  return (
    <div
      className={cn(
        "rounded-xl border transition-all duration-150 glass-dark cursor-pointer",
        cfg.border,
        cfg.bg,
        selected && "ring-1 ring-white/25 shadow-lg",
        isLarge ? "px-4 py-3 min-w-[170px]" : "px-3 py-2.5 min-w-[130px]",
      )}
    >
      <Handle type="target" position={Position.Top} style={{ opacity: 0, width: 8, height: 8 }} />
      <div className="flex items-center gap-2">
        <Icon className={cn("flex-shrink-0", isLarge ? "w-4 h-4" : "w-3.5 h-3.5", cfg.iconColor)} />
        <span className={cn("font-medium text-slate-200 leading-tight truncate max-w-[140px]", isLarge ? "text-sm" : "text-xs")}>
          {d.label}
        </span>
      </div>
      {d.subtitle && (
        <p className="text-[10px] text-slate-500 mt-0.5 pl-6 truncate">{d.subtitle}</p>
      )}
      {d.tags && d.tags.length > 0 && (
        <div className="flex gap-1 mt-1.5 pl-6 flex-wrap">
          {d.tags.slice(0, 3).map((t) => (
            <span key={t} className="text-[9px] px-1.5 py-px rounded-full bg-white/5 text-slate-500 border border-white/8">
              {t}
            </span>
          ))}
        </div>
      )}
      <Handle type="source" position={Position.Bottom} style={{ opacity: 0, width: 8, height: 8 }} />
    </div>
  );
});
WorldNode.displayName = "WorldNode";

const nodeTypes = { worldNode: WorldNode };

function InspectorPanel({ node, onFocusEntity }: { node: Node<GraphNodeData> | null; onFocusEntity?: (id: string, label: string) => void }) {
  if (!node) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center text-center px-6 gap-3">
        <Network className="w-10 h-10 text-slate-800" />
        <p className="text-sm text-slate-500">Select a node</p>
        <p className="text-xs text-slate-700 leading-relaxed">
          Click any entity in the graph to inspect and edit it.
        </p>
      </div>
    );
  }

  const cfg = KIND_CONFIG[node.data.kind as GraphNodeKind];
  const Icon = cfg.icon;

  return (
    <div className="flex-1 overflow-y-auto p-4 space-y-4">
      <div className="flex items-start gap-3">
        <div className={cn("p-2.5 rounded-xl border flex-shrink-0", cfg.bg, cfg.border)}>
          <Icon className={cn("w-5 h-5", cfg.iconColor)} />
        </div>
        <div className="flex-1 min-w-0">
          <h2 className="text-base font-semibold text-slate-100 leading-tight truncate">
            {node.data.label}
          </h2>
          <span className={cn("text-[10px] mt-1 inline-block", cfg.tagClass)}>{cfg.label}</span>
        </div>
      </div>

      {node.data.description && (
        <div>
          <p className="text-[10px] text-slate-600 uppercase tracking-wider mb-1.5">Description</p>
          <p className="text-sm text-slate-400 leading-relaxed">{node.data.description}</p>
        </div>
      )}

      {node.data.subtitle && (
        <div>
          <p className="text-[10px] text-slate-600 uppercase tracking-wider mb-1.5">Details</p>
          <p className="text-sm text-slate-400">{node.data.subtitle}</p>
        </div>
      )}

      {(node.data.tags ?? []).length > 0 && (
        <div>
          <p className="text-[10px] text-slate-600 uppercase tracking-wider mb-2">Tags</p>
          <div className="flex flex-wrap gap-1.5">
            {(node.data.tags ?? []).map((t) => (
              <span key={t} className="tag-dim">{t}</span>
            ))}
          </div>
        </div>
      )}

      <div>
        <p className="text-[10px] text-slate-600 uppercase tracking-wider mb-1">ID</p>
        <p className="font-mono text-xs text-slate-700">{node.id}</p>
      </div>

      <div className="flex gap-2 pt-1">
        {onFocusEntity && !["multiverse", "universe"].includes(node.data.kind) && (
          <button
            onClick={() => onFocusEntity(node.id, node.data.label)}
            className="btn-ghost flex-1 justify-center text-xs py-1.5 text-purple-400 hover:text-purple-300 border border-purple-500/20"
            title="Show connections"
          >
            <Link2 className="w-3.5 h-3.5" />
            Focus
          </button>
        )}
        {node.data.kind === "universe" && (
          <a
            href={`/worlds?universe=${node.id}`}
            className="btn-cyber flex-1 justify-center text-xs py-1.5"
            title="Open in the tree with stories and scenes"
          >
            <Globe2 className="w-3.5 h-3.5" />
            Open tree
          </a>
        )}
      </div>
    </div>
  );
}

function GraphLegend() {
  return (
    <div className="glass-dark rounded-xl border border-white/5 p-3 space-y-1.5">
      {(["multiverse", "universe", "character", "location", "faction", "concept"] as GraphNodeKind[]).map((kind) => {
        const cfg = KIND_CONFIG[kind];
        const Icon = cfg.icon;
        return (
          <div key={kind} className="flex items-center gap-2">
            <Icon className={cn("w-3 h-3 flex-shrink-0", cfg.iconColor)} />
            <span className="text-[10px] text-slate-500">{cfg.label}</span>
          </div>
        );
      })}
    </div>
  );
}

function GraphCanvas({
  initialNodes,
  initialEdges,
  onNodeSelect,
}: {
  initialNodes: Node<GraphNodeData>[];
  initialEdges: Edge[];
  onNodeSelect: (node: Node<GraphNodeData> | null) => void;
}) {
  const [nodes, setNodes, onNodesChange] = useNodesState<Node<GraphNodeData>>(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);

  // Sync when data arrives after mount (useNodesState only reads initial value once)
  useEffect(() => { setNodes(initialNodes); }, [initialNodes, setNodes]);
  useEffect(() => { setEdges(initialEdges); }, [initialEdges, setEdges]);

  const onNodeClick = useCallback((_evt: React.MouseEvent, node: Node) => {
    onNodeSelect(node as Node<GraphNodeData>);
  }, [onNodeSelect]);

  const onPaneClick = useCallback(() => {
    onNodeSelect(null);
  }, [onNodeSelect]);

  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      onNodesChange={onNodesChange}
      onEdgesChange={onEdgesChange}
      onNodeClick={onNodeClick}
      onPaneClick={onPaneClick}
      nodeTypes={nodeTypes}
      colorMode="dark"
      fitView
      fitViewOptions={{ padding: 0.15 }}
      defaultEdgeOptions={{
        style: { stroke: "rgba(0, 212, 255, 0.35)", strokeWidth: 1.5 },
        labelStyle: { fill: "#64748b", fontSize: 10 },
        labelBgStyle: { fill: "rgba(5, 5, 14, 0.85)", fillOpacity: 1 },
        labelBgPadding: [4, 6],
        labelBgBorderRadius: 4,
      }}
    >
      <Background variant={BackgroundVariant.Dots} gap={28} size={1} color="rgba(148,163,184,0.04)" />
      <Controls showInteractive={false} />
      <MiniMap
        nodeColor={(n) => {
          const k = (n.data as GraphNodeData)?.kind;
          const colors: Record<GraphNodeKind, string> = {
            multiverse: "rgba(168,85,247,0.7)",
            universe: "rgba(0,212,255,0.7)",
            character: "rgba(0,212,255,0.45)",
            location: "rgba(245,158,11,0.55)",
            faction: "rgba(16,185,129,0.55)",
            concept: "rgba(236,72,153,0.45)",
            axiom: "rgba(99,102,241,0.45)",
            lore: "rgba(245,158,11,0.35)",
            rule: "rgba(100,116,139,0.45)",
            pack: "rgba(20,184,166,0.45)",
          };
          return colors[k as GraphNodeKind] ?? "rgba(100,116,139,0.45)";
        }}
        maskColor="rgba(5,5,14,0.88)"
        style={{ borderRadius: 8 }}
      />
    </ReactFlow>
  );
}

function GraphTab() {
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
                      placeholder="Search an entity to see its connections…"
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

function CreateMultiverseForm({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated?: (mv: Multiverse) => void;
}) {
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [desc, setDesc] = useState("");

  const mut = useMutation({
    mutationFn: () => universesApi.createMultiverse({ name, description: desc || undefined }),
    onSuccess: (created) => {
      qc.invalidateQueries({ queryKey: ["multiverses"] });
      onCreated?.(created);
      onClose();
    },
  });

  return (
    <motion.div
      initial={{ opacity: 0, y: -6 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -6 }}
      className="glass-dark rounded-xl border border-purple-500/20 p-4 space-y-3"
    >
      <div className="flex items-center justify-between">
        <p className="text-xs font-semibold text-purple-300">New Multiverse</p>
        <button onClick={onClose} className="text-slate-600 hover:text-slate-300">
          <X className="w-3.5 h-3.5" />
        </button>
      </div>
      <input
        className="input-cyber w-full"
        placeholder="Name…"
        value={name}
        onChange={(e) => setName(e.target.value)}
        autoFocus
      />
      <input
        className="input-cyber w-full"
        placeholder="Description (optional)"
        value={desc}
        onChange={(e) => setDesc(e.target.value)}
      />
      <button
        onClick={() => mut.mutate()}
        disabled={!name.trim() || mut.isPending}
        className="btn-cyber w-full justify-center"
      >
        {mut.isPending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Plus className="w-3.5 h-3.5" />}
        Create
      </button>
    </motion.div>
  );
}

function CreateUniverseForm({
  multiverseId,
  onClose,
  onCreated,
}: {
  multiverseId: string;
  onClose: () => void;
  onCreated?: (universe: Universe) => void;
}) {
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [genre, setGenre] = useState("");
  const [desc, setDesc] = useState("");

  const mut = useMutation({
    mutationFn: () =>
      universesApi.createUniverse({
        name,
        multiverse_id: multiverseId,
        genre: genre || undefined,
        description: desc || undefined,
      }),
    onSuccess: (created) => {
      qc.invalidateQueries({ queryKey: ["universes"] });
      qc.invalidateQueries({ queryKey: ["multiverses"] });
      onCreated?.(created);
      onClose();
    },
  });

  const GENRES = ["Fantasy", "Sci-Fi", "Horror", "Cyberpunk", "Historical", "Modern", "Mystery", "Western", "Superhero"];

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.97 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0 }}
      className="glass rounded-2xl border border-cyan-500/20 p-5 space-y-4"
    >
      <div className="flex items-center justify-between">
        <p className="text-sm font-semibold text-slate-200">New Universe</p>
        <button onClick={onClose} className="text-slate-600 hover:text-slate-300">
          <X className="w-4 h-4" />
        </button>
      </div>

      <input
        className="input-cyber w-full"
        placeholder="Universe name…"
        value={name}
        onChange={(e) => setName(e.target.value)}
        autoFocus
      />

      <div>
        <p className="text-xs text-slate-600 mb-2">Genre</p>
        <div className="flex flex-wrap gap-2">
          {GENRES.map((g) => (
            <button
              key={g}
              onClick={() => setGenre(genre === g ? "" : g)}
              className={cn(
                "text-xs px-2.5 py-1 rounded-full border transition-all",
                genre === g
                  ? "bg-cyan-500/15 border-cyan-500/40 text-cyan-300"
                  : "border-white/10 text-slate-500 hover:border-white/20 hover:text-slate-300",
              )}
            >
              {g}
            </button>
          ))}
        </div>
      </div>

      <textarea
        className="input-cyber w-full resize-none"
        rows={2}
        placeholder="Short description (optional)"
        value={desc}
        onChange={(e) => setDesc(e.target.value)}
      />

      <button
        onClick={() => mut.mutate()}
        disabled={!name.trim() || mut.isPending}
        className="btn-cyber w-full justify-center"
      >
        {mut.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Globe2 className="w-4 h-4" />}
        Create Universe
      </button>
    </motion.div>
  );
}

function HierarchyTab() {
  const qc = useQueryClient();
  const searchParams = useSearchParams();
  const world = useWorldContext();
  // URL deep link wins; otherwise open the tree at the global world (T-077)
  const requestedUniverseId = searchParams.get("universe") ?? world.universeId;
  const [showMvForm, setShowMvForm] = useState(false);
  const [createUnderMvId, setCreateUnderMvId] = useState<string | null>(null);

  const { data: multiverses = [], isLoading: mvLoading } = useQuery({
    queryKey: ["multiverses"],
    queryFn: universesApi.listMultiverses,
  });

  const deleteUnivMut = useMutation({
    mutationFn: universesApi.deleteUniverse,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["universes"] });
      qc.invalidateQueries({ queryKey: ["multiverses"] });
    },
  });

  return (
    <div className="flex flex-col h-full">
      {/* Toolbar */}
      <div className="flex items-center gap-3 px-4 h-11 border-b border-white/5 glass-dark flex-shrink-0">
        {mvLoading ? (
          <span className="flex items-center gap-1.5 text-xs text-slate-600">
            <Loader2 className="w-3 h-3 animate-spin" /> loading…
          </span>
        ) : (
          <span className="text-xs text-slate-600">
            {multiverses.length} setting{multiverses.length !== 1 ? "s" : ""} · traverse settings →
            universes → stories → scenes
          </span>
        )}
        <div className="flex-1" />
        <div className="flex items-center gap-2">
          <select
            value={createUnderMvId ?? ""}
            onChange={(e) => setCreateUnderMvId(e.target.value || null)}
            className="input-cyber py-1 text-xs min-w-[150px]"
            title="Create a universe inside this setting"
          >
            <option value="">New universe in…</option>
            {multiverses.map((mv) => (
              <option key={mv.id} value={mv.id}>{mv.name}</option>
            ))}
          </select>
          <button onClick={() => setShowMvForm((v) => !v)} className="btn-cyber text-xs py-1.5">
            <Plus className="w-3.5 h-3.5" /> New Multiverse
          </button>
        </div>
      </div>

      {/* Create forms */}
      <AnimatePresence>
        {(showMvForm || createUnderMvId) && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.15 }}
            className="overflow-hidden border-b border-white/5 flex-shrink-0"
          >
            <div className="px-4 py-3 max-w-lg">
              {showMvForm ? (
                <CreateMultiverseForm
                  onClose={() => setShowMvForm(false)}
                  onCreated={(mv) => {
                    setShowMvForm(false);
                    setCreateUnderMvId(mv.id);
                  }}
                />
              ) : createUnderMvId ? (
                <CreateUniverseForm
                  multiverseId={createUnderMvId}
                  onClose={() => setCreateUnderMvId(null)}
                  onCreated={() => {
                    qc.invalidateQueries({ queryKey: ["universes"] });
                    qc.invalidateQueries({ queryKey: ["multiverses"] });
                    setCreateUnderMvId(null);
                  }}
                />
              ) : null}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Tree + detail */}
      <div className="flex-1 overflow-hidden">
        {multiverses.length === 0 && !mvLoading ? (
          <div className="flex flex-col items-center justify-center h-full space-y-3">
            <div className="w-16 h-16 rounded-2xl bg-purple-500/10 border border-purple-500/20 flex items-center justify-center shadow-purple-glow">
              <Layers className="w-8 h-8 text-purple-400" />
            </div>
            <p className="text-sm font-medium text-slate-300">Create a setting first</p>
            <p className="text-xs text-slate-600 text-center max-w-xs">
              Start by creating a multiverse. Universes, stories, and scenes will live inside it.
            </p>
            <button onClick={() => setShowMvForm(true)} className="btn-cyber mt-2">
              <Plus className="w-4 h-4" /> Create Multiverse
            </button>
          </div>
        ) : (
          <UniverseTree
            multiverses={multiverses}
            requestedUniverseId={requestedUniverseId}
            onDeleteUniverse={(id) => deleteUnivMut.mutate(id)}
          />
        )}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
//  ENTITIES TAB (from /npcs)
// ═══════════════════════════════════════════════════════════════

function NPCCard({ npc, onClick }: { npc: NPC; onClick: () => void }) {
  const typeConfig: Record<string, { color: string; icon: React.ElementType }> = {
    character: { color: "tag-purple", icon: User },
    npc: { color: "tag-cyan", icon: User },
    creature: { color: "tag-amber", icon: User },
    location: { color: "tag-amber", icon: MapPin },
    faction: { color: "tag-emerald", icon: Shield },
    organization: { color: "tag-emerald", icon: Users },
    concept: { color: "tag-dim", icon: Sparkles },
    object: { color: "tag-dim", icon: MemoryStick },
  };
  const cfg = typeConfig[npc.entity_type?.toLowerCase()] ?? { color: "tag-dim", icon: Sparkles };
  const TypeIcon = cfg.icon;

  return (
    <motion.button
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      whileHover={{ y: -2 }}
      onClick={onClick}
      className="glass w-full text-left rounded-2xl border border-white/5 hover:border-cyan-500/20 hover:shadow-cyan-glow p-5 space-y-3 transition-all duration-200 group"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-full bg-purple-500/10 border border-purple-500/25 flex items-center justify-center flex-shrink-0">
            <TypeIcon className="w-5 h-5 text-purple-400" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-slate-100 group-hover:text-cyan-200 transition-colors">
              {npc.name}
            </h3>
            <span className={cn("text-[10px] capitalize", cfg.color)}>{npc.entity_type}</span>
          </div>
        </div>
        <ChevronRight className="w-4 h-4 text-slate-600 group-hover:text-cyan-400 transition-colors mt-0.5" />
      </div>

      {npc.description && (
        <p className="text-xs text-slate-500 leading-relaxed">
          {truncate(npc.description, 100)}
        </p>
      )}

      {npc.state_tags.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {npc.state_tags.slice(0, 4).map((t) => (
            <span key={t} className="tag-dim">{t}</span>
          ))}
          {npc.state_tags.length > 4 && (
            <span className="tag-dim">+{npc.state_tags.length - 4}</span>
          )}
        </div>
      )}

      <div className="flex items-center justify-between pt-1 border-t border-white/5">
        <div className="flex items-center gap-1.5 text-xs text-slate-600 capitalize">
          <TypeIcon className="w-3 h-3" />
          <span>{npc.entity_type}</span>
        </div>
        <span className={cn("text-[10px]",
          npc.canon_level === "canon" ? "text-cyan-500/60" : "text-slate-600"
        )}>
          {npc.canon_level}
        </span>
      </div>
    </motion.button>
  );
}

function NPCDetailPanel({ npcId, onClose }: { npcId: string; onClose: () => void }) {
  const { data: npc, isLoading } = useQuery({
    queryKey: ["npc", npcId],
    queryFn: () => entitiesApi.getNPC(npcId),
    enabled: !!npcId,
  });

  return (
    <motion.div
      initial={{ x: "100%" }}
      animate={{ x: 0 }}
      exit={{ x: "100%" }}
      transition={{ type: "spring", stiffness: 320, damping: 32 }}
      className="fixed right-0 top-0 h-full w-80 glass border-l border-white/5 flex flex-col z-20 overflow-hidden"
    >
      <div className="flex items-center justify-between px-5 py-4 border-b border-white/5">
        <span className="text-sm font-semibold text-slate-200">
          {isLoading ? "Loading…" : npc?.name ?? "NPC"}
        </span>
        <button onClick={onClose} className="text-slate-600 hover:text-slate-200">
          <X className="w-4 h-4" />
        </button>
      </div>

      {isLoading && (
        <div className="flex-1 flex items-center justify-center">
          <Loader2 className="w-6 h-6 text-cyan-400 animate-spin" />
        </div>
      )}

      {npc && (
        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-5">
          <div className="flex items-center gap-4">
            <div className="w-16 h-16 rounded-full bg-purple-500/10 border border-purple-500/25 flex items-center justify-center">
              <User className="w-8 h-8 text-purple-400" />
            </div>
            <div>
              <p className="text-base font-semibold text-slate-100">{npc.name}</p>
              <span className="tag-purple">{npc.entity_type}</span>
            </div>
          </div>

          {npc.description && (
            <p className="text-xs text-slate-400 leading-relaxed">{npc.description}</p>
          )}

          {Object.keys(npc.properties).length > 0 && (
            <div className="space-y-2">
              <p className="section-label">Properties</p>
              {Object.entries(npc.properties).map(([k, v]) => (
                <div key={k} className="flex items-start justify-between gap-2 text-xs">
                  <span className="text-slate-600 capitalize">{k.replace(/_/g, " ")}</span>
                  <span className="font-mono text-slate-300 text-right max-w-[60%] break-all">
                    {typeof v === "object" ? JSON.stringify(v) : String(v)}
                  </span>
                </div>
              ))}
            </div>
          )}

          {Object.keys(npc.stats).length > 0 && (
            <div className="space-y-3">
              <p className="section-label">Stats</p>
              {Object.entries(npc.stats as Record<string, number>).map(([k, v]) => (
                <div key={k} className="space-y-1">
                  <div className="flex items-center justify-between text-xs">
                    <span className="text-slate-500 capitalize">{k}</span>
                    <span className="font-mono text-cyan-300">{v}</span>
                  </div>
                  {typeof v === "number" && v <= 100 && (
                    <div className="stat-bar-track">
                      <div className="stat-bar-fill bg-cyan-500" style={{ width: `${v}%` }} />
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}

          {npc.state_tags.length > 0 && (
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <Tag className="w-3 h-3 text-slate-500" />
                <p className="section-label">State Tags</p>
              </div>
              <div className="flex flex-wrap gap-1.5">
                {npc.state_tags.map((t) => (
                  <span key={t} className="tag-dim">{t}</span>
                ))}
              </div>
            </div>
          )}

          {npc.memories.length > 0 && (
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <Brain className="w-3 h-3 text-slate-500" />
                <p className="section-label">Memories ({npc.memories.length})</p>
              </div>
              <div className="space-y-2">
                {npc.memories.slice(0, 8).map((m) => (
                  <div key={m.id} className="glass-dark rounded-lg p-3 border border-white/5">
                    <p className="text-xs text-slate-300 leading-relaxed">{m.content}</p>
                    <div className="flex items-center justify-between mt-2">
                      <span className="tag-dim">{m.memory_type}</span>
                      <span className="text-[10px] text-slate-600">{formatRelativeTime(m.timestamp)}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {npc.relationships.length > 0 && (
            <div className="space-y-2">
              <p className="section-label">Relationships</p>
              {npc.relationships.slice(0, 6).map((r, i) => (
                <div key={i} className="flex items-center gap-2 text-xs text-slate-400">
                  <div className="w-1.5 h-1.5 rounded-full bg-purple-500 flex-shrink-0" />
                  <span>{String(r.target_name ?? r.target ?? "Unknown")}</span>
                  <span className="text-slate-600 ml-auto">{String(r.relation_type ?? r.type ?? "")}</span>
                </div>
              ))}
            </div>
          )}

          {npc.facts && npc.facts.length > 0 && (
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <Sparkles className="w-3 h-3 text-slate-500" />
                <p className="section-label">Lore ({npc.facts.length})</p>
              </div>
              <div className="space-y-2">
                {npc.facts.map((f) => (
                  <div key={f.id} className="glass-dark rounded-lg p-3 border border-white/5">
                    <p className="text-xs text-slate-300 leading-relaxed">{f.statement}</p>
                    <div className="flex items-center justify-between mt-1.5">
                      <span className="tag-dim capitalize">{f.fact_type}</span>
                      <span className="text-[10px] text-slate-700">{Math.round(f.confidence * 100)}% conf</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </motion.div>
  );
}

function EntitiesTab() {
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [page, setPage] = useState(0);
  const [activeType, setActiveType] = useState<string | null>(null);
  const LIMIT = 20;

  const ENTITY_TYPE_OPTIONS: Array<{ type: string; icon: React.ElementType; color: string }> = [
    { type: "character", icon: User, color: "text-cyan-300 border-cyan-500/25 bg-cyan-500/8" },
    { type: "location", icon: MapPin, color: "text-amber-400 border-amber-500/25 bg-amber-500/8" },
    { type: "faction", icon: Shield, color: "text-emerald-400 border-emerald-500/25 bg-emerald-500/8" },
    { type: "organization", icon: Users, color: "text-emerald-400 border-emerald-500/25 bg-emerald-500/8" },
    { type: "concept", icon: Sparkles, color: "text-pink-400 border-pink-500/25 bg-pink-500/8" },
    { type: "object", icon: MemoryStick, color: "text-pink-400 border-pink-500/25 bg-pink-500/8" },
    { type: "creature", icon: User, color: "text-amber-400 border-amber-500/25 bg-amber-500/8" },
  ];

  const { data, isLoading } = useQuery({
    queryKey: ["entities", query, page, activeType],
    queryFn: () =>
      entitiesApi.listNPCs({
        q: query || undefined,
        entity_type: activeType ?? undefined,
        limit: LIMIT,
        offset: page * LIMIT,
      }),
    staleTime: 15_000,
  });

  const npcs = data?.items ?? [];
  const total = data?.total ?? 0;

  return (
    <div className="flex-1 flex overflow-hidden">
      <div className="flex-1 overflow-y-auto px-8 py-6 space-y-6">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 className="text-lg font-bold text-slate-100">Entities</h2>
            <p className="text-sm text-slate-500 mt-1">
              {total > 0 ? `${total.toLocaleString()} entities in the knowledge graph.` : "Browse entities stored in the knowledge graph."}
            </p>
          </div>
        </div>

        {/* Type filter chips */}
        <div className="flex items-center gap-2 flex-wrap">
          <button
            onClick={() => { setActiveType(null); setPage(0); }}
            className={cn(
              "text-xs px-3 py-1.5 rounded-lg border transition-all",
              activeType === null
                ? "bg-white/8 border-white/15 text-slate-200"
                : "border-transparent text-slate-600 hover:text-slate-300",
            )}
          >
            All
          </button>
          {ENTITY_TYPE_OPTIONS.map(({ type, icon: Icon, color }) => (
            <button
              key={type}
              onClick={() => { setActiveType(activeType === type ? null : type); setPage(0); }}
              className={cn(
                "flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg border transition-all capitalize",
                activeType === type ? color : "border-transparent text-slate-600 hover:text-slate-300",
              )}
            >
              <Icon className="w-3 h-3" />
              {type}
            </button>
          ))}
        </div>

        <div className="flex gap-3">
          <div className="relative flex-1 max-w-md">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-600" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && (setQuery(search), setPage(0))}
              placeholder="Search by name or description…"
              className="input-cyber pl-9"
            />
          </div>
          <button onClick={() => { setQuery(search); setPage(0); }} className="btn-cyber">
            Search
          </button>
          {(query || activeType) && (
            <button onClick={() => { setSearch(""); setQuery(""); setActiveType(null); setPage(0); }} className="btn-ghost">
              <X className="w-4 h-4" /> Clear
            </button>
          )}
        </div>

        {isLoading && (
          <div className="flex items-center gap-2 text-slate-500 text-sm">
            <Loader2 className="w-4 h-4 animate-spin" /> Querying knowledge graph…
          </div>
        )}

        {npcs.length === 0 && !isLoading && (
          <div className="flex flex-col items-center justify-center py-24 space-y-3">
            <Users className="w-12 h-12 text-slate-700" />
            <p className="text-slate-500 text-sm">
              {query
                ? `No entities matching "${query}".`
                : "No entities found. Ingest source documents to populate the knowledge graph."}
            </p>
          </div>
        )}

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {npcs.map((npc) => (
            <NPCCard key={npc.id} npc={npc} onClick={() => setSelectedId(npc.id)} />
          ))}
        </div>

        {total > LIMIT && (
          <div className="flex items-center justify-center gap-3 pt-4">
            <button
              disabled={page === 0}
              onClick={() => setPage((p) => p - 1)}
              className="btn-ghost disabled:opacity-30"
            >
              Previous
            </button>
            <span className="text-xs text-slate-500">
              Page {page + 1} of {Math.ceil(total / LIMIT)}
            </span>
            <button
              disabled={(page + 1) * LIMIT >= total}
              onClick={() => setPage((p) => p + 1)}
              className="btn-ghost disabled:opacity-30"
            >
              Next
            </button>
          </div>
        )}
      </div>

      <AnimatePresence>
        {selectedId && (
          <NPCDetailPanel npcId={selectedId} onClose={() => setSelectedId(null)} />
        )}
      </AnimatePresence>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
//  MAIN PAGE
// ═══════════════════════════════════════════════════════════════

function WorldsPageContent() {
  const searchParams = useSearchParams();
  // Deep links carrying ?universe= land on the tree so the target is visible
  const [tab, setTab] = useState<WorldTab>(searchParams.get("universe") ? "hierarchy" : "graph");

  return (
    <div className="flex flex-col h-full">
      {/* Header + Tabs */}
      <div className="flex items-center gap-4 px-6 py-3 border-b border-white/5 glass-dark flex-shrink-0">
        <Globe2 className="w-5 h-5 text-purple-400 flex-shrink-0" />
        <h1 className="text-sm font-bold text-slate-200">Worlds</h1>
        <div className="h-5 w-px bg-white/10" />
        <div className="flex items-center gap-1">
          {WORLD_TABS.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              onClick={() => setTab(id)}
              className={cn(
                "flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium transition-all",
                tab === id
                  ? "bg-purple-500/10 text-purple-300 border border-purple-500/25"
                  : "text-slate-500 hover:text-slate-300 border border-transparent",
              )}
            >
              <Icon className="w-3.5 h-3.5" />
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* Tab content */}
      <div className="flex-1 overflow-hidden">
        {tab === "graph" && <GraphTab />}
        {tab === "hierarchy" && <HierarchyTab />}
        {tab === "entities" && <EntitiesTab />}
      </div>
    </div>
  );
}

export default function WorldsPage() {
  return (
    <Suspense fallback={<div className="p-6 text-sm text-slate-500">Loading worlds…</div>}>
      <WorldsPageContent />
    </Suspense>
  );
}
