"use client";

import { Suspense, memo, useCallback, useEffect, useState, useMemo } from "react";
import Link from "next/link";
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
  Save,
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
  NPC,
  NPCDetail,
  WorldGraphFilter,
} from "@/lib/types";
import { cn, formatRelativeTime, truncate } from "@/lib/utils";
import { UniverseTree } from "@/components/worlds/UniverseTree";
import { CreateMultiverseForm } from "@/components/forge/worlds/CreateMultiverseForm";
import { CreateUniverseForm } from "@/components/forge/worlds/CreateUniverseForm";
import { useWorldContext, repairWorldSelection } from "@/lib/world-context";
import { NPCCard } from "./NPCCard";
import { NPCDetailPanel } from "./NPCDetailPanel";
import { GraphLegend } from "./GraphLegend";
import { InspectorPanel } from "./InspectorPanel";
import { GraphTab } from "./GraphTab";

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
    onSuccess: (_data, id) => {
      qc.invalidateQueries({ queryKey: ["universes"] });
      qc.invalidateQueries({ queryKey: ["multiverses"] });
      // Repair the persisted world selection if it pointed at this universe (F3-3 phase 7)
      world.setWorld(repairWorldSelection(world, { universeId: id }));
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
          <Link
            href="/forge/worlds/new"
            className="btn-cyber text-xs py-1.5"
            title="Open the world-creation wizard (F1-3)"
          >
            <Plus className="w-3.5 h-3.5" /> New world
          </Link>
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
              placeholder="Search by name or description…" aria-label="Search by name or description"
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
