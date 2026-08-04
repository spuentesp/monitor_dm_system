"use client";

import { Suspense, useState, useMemo, useCallback, type MouseEvent as ReactMouseEvent } from "react";
import { useSearchParams } from "next/navigation";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  addEdge,
  useNodesState,
  useEdgesState,
  BackgroundVariant,
  Handle,
  Position,
  type NodeProps,
  type Node,
  type Edge,
  type Connection,
} from "@xyflow/react";
import { toReactFlowNode, toReactFlowEdge, toReactFlowGraph } from "@/features/graph/adapters";
import "@xyflow/react/dist/style.css";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Brain,
  Compass,
  Filter,
  GitBranch,
  Layers,
  Link2,
  Loader2,
  MapPin,
  Network,
  Pencil,
  Plus,
  RefreshCw,
  Search,
  Shield,
  Sparkles,
  Tag,
  Trash2,
  WifiOff,
  X,
  Zap,
  User as UserIcon,
} from "lucide-react";
import { DialogFooter, DialogShell } from "@/components/DialogShell";
import { entitiesApi, graphApi, universesApi } from "@/lib/api";
import type {
  EntityRelationship,
  GraphNodeData,
  GraphNodeKind,
  Multiverse,
  Universe,
  WorldGraph,
} from "@/lib/types";
import { cn, truncate } from "@/lib/utils";

// ─── Node renderer ─────────────────────────────────────────
//
// The Explorer was rendering default xyflow nodes — plain white rectangles
// with no styling, no labels, no entity-type colors. This config + renderer
// matches the Architect/Worlds WorldNode: colored border + icon + label +
// subtitle + tags, with selection and connection handles.

const NODE_KIND_CONFIG: Record<
  GraphNodeKind,
  { border: string; bg: string; icon: React.ElementType; iconColor: string }
> = {
  multiverse: { border: "border-purple-500/40", bg: "bg-purple-500/10", icon: Layers, iconColor: "text-purple-400" },
  universe:   { border: "border-cyan-500/40",   bg: "bg-cyan-500/10",   icon: Compass, iconColor: "text-cyan-400" },
  character:  { border: "border-emerald-500/40", bg: "bg-emerald-500/10", icon: UserIcon, iconColor: "text-emerald-400" },
  location:   { border: "border-amber-500/40",   bg: "bg-amber-500/10",   icon: MapPin,  iconColor: "text-amber-400" },
  faction:    { border: "border-red-500/40",     bg: "bg-red-500/10",     icon: Shield,  iconColor: "text-red-400" },
  concept:    { border: "border-violet-500/40",  bg: "bg-violet-500/10",  icon: Brain,   iconColor: "text-violet-400" },
  axiom:      { border: "border-slate-500/40",   bg: "bg-slate-500/10",   icon: Zap,     iconColor: "text-slate-300" },
  lore:       { border: "border-teal-500/40",    bg: "bg-teal-500/10",    icon: Tag,     iconColor: "text-teal-400" },
  rule:       { border: "border-orange-500/40",  bg: "bg-orange-500/10",  icon: Sparkles, iconColor: "text-orange-400" },
  pack:       { border: "border-pink-500/40",    bg: "bg-pink-500/10",    icon: Layers,  iconColor: "text-pink-400" },
};

const GraphNodeRenderer = ({ data, selected }: NodeProps) => {
  const d = data as GraphNodeData;
  const cfg = NODE_KIND_CONFIG[d.kind] ?? NODE_KIND_CONFIG.concept;
  const Icon = cfg.icon;
  const isLarge = d.kind === "multiverse" || d.kind === "universe";

  return (
    <div
      className={cn(
        "rounded-xl border transition-all duration-150 cursor-pointer",
        cfg.border,
        cfg.bg,
        selected && "ring-1 ring-white/30 shadow-lg",
        isLarge ? "px-4 py-3 min-w-[170px]" : "px-3 py-2.5 min-w-[140px]",
      )}
    >
      <Handle type="target" position={Position.Top} className="!border-0 !bg-white/20 !w-2 !h-2" />
      <div className="flex items-center gap-2">
        <Icon className={cn("flex-shrink-0", isLarge ? "w-4 h-4" : "w-3.5 h-3.5", cfg.iconColor)} />
        <span
          className={cn(
            "font-medium text-slate-100 leading-tight truncate max-w-[160px]",
            isLarge ? "text-sm" : "text-xs",
          )}
        >
          {d.label}
        </span>
      </div>
      {d.subtitle && (
        <p className={cn("text-slate-400 mt-0.5 pl-6 truncate", isLarge ? "text-[11px]" : "text-[10px]")}>
          {d.subtitle}
        </p>
      )}
      {d.tags && d.tags.length > 0 && (
        <div className="flex gap-1 mt-1.5 pl-6 flex-wrap">
          {d.tags.slice(0, 3).map((t) => (
            <span
              key={t}
              className="text-[9px] px-1.5 py-px rounded-full bg-white/5 text-slate-400 border border-white/10"
            >
              {t}
            </span>
          ))}
        </div>
      )}
      <Handle type="source" position={Position.Bottom} className="!border-0 !bg-white/20 !w-2 !h-2" />
    </div>
  );
};

const nodeTypes = { worldNode: GraphNodeRenderer };

// Node fill for the MiniMap — same colors as the node renderer.
const nodeFillForKind = (kind: GraphNodeKind | undefined): string => {
  switch (kind) {
    case "multiverse": return "rgba(168, 85, 247, 0.7)";
    case "universe":   return "rgba(0, 212, 255, 0.7)";
    case "character":  return "rgba(16, 185, 129, 0.7)";
    case "location":   return "rgba(245, 158, 11, 0.7)";
    case "faction":    return "rgba(239, 68, 68, 0.7)";
    case "concept":    return "rgba(139, 92, 246, 0.7)";
    case "axiom":      return "rgba(148, 163, 184, 0.7)";
    case "lore":       return "rgba(20, 184, 166, 0.7)";
    case "rule":       return "rgba(251, 146, 60, 0.7)";
    case "pack":       return "rgba(236, 72, 153, 0.7)";
    default:           return "rgba(148, 163, 184, 0.5)";
  }
};

const ENTITY_TYPES = [
  { id: "character", label: "Characters" },
  { id: "location", label: "Locations" },
  { id: "faction", label: "Factions" },
  { id: "concept", label: "Concepts" },
] as const;

type EntityTypeId = (typeof ENTITY_TYPES)[number]["id"];

// Relationship types the user can draw between nodes (M-37). Category is
// inferred server-side from the type.
const REL_TYPES = [
  "RELATED_TO",
  "ALLIED_WITH",
  "HOSTILE_TO",
  "KNOWS",
  "MEMBER_OF",
  "LEADS",
  "WORKS_FOR",
  "OWNS",
  "LOCATED_IN",
  "CONTAINS",
  "CONTROLS",
  "REVERES",
] as const;

// Relationship categories editable on existing edges (F2-2 phase 4). The
// rel_type itself is structural and can't be changed by the update API.
const REL_CATEGORIES = [
  "social",
  "membership",
  "ownership",
  "spatial",
  "temporal",
  "taxonomic",
  "power",
  "generic",
] as const;

export default function ExplorerPage() {
  return (
    <Suspense fallback={null}>
      <ExplorerPageInner />
    </Suspense>
  );
}

function ExplorerPageInner() {
  const params = useSearchParams();
  const initialUniverse = params.get("universe");

  // ─── Scope ────────────────────────────────────────────────
  const [multiverseId, setMultiverseId] = useState<string | null>(null);
  const [universeId, setUniverseId] = useState<string | null>(initialUniverse);

  // ─── Filter state ─────────────────────────────────────────
  const [depth, setDepth] = useState(2);
  const [enabledTypes, setEnabledTypes] = useState<Set<EntityTypeId>>(
    () => new Set(ENTITY_TYPES.map((t) => t.id)),
  );
  const [search, setSearch] = useState("");

  // ─── Lookups ──────────────────────────────────────────────
  const multiversesQ = useQuery({
    queryKey: ["multiverses"],
    queryFn: () => universesApi.listMultiverses(),
  });
  const universesQ = useQuery({
    queryKey: ["universes", multiverseId],
    queryFn: () => universesApi.listUniverses(multiverseId ?? undefined),
    enabled: !!multiverseId,
  });

  if (!multiverseId && multiversesQ.data && multiversesQ.data.length > 0) {
    setMultiverseId(multiversesQ.data[0].id);
  }
  if (
    multiverseId &&
    !universeId &&
    universesQ.data &&
    universesQ.data.length > 0
  ) {
    setUniverseId(universesQ.data[0].id);
  }

  // ─── Graph data ───────────────────────────────────────────
  const graphQ = useQuery({
    queryKey: ["universeGraph", universeId, depth, [...enabledTypes].join(",")],
    queryFn: () =>
      graphApi.getUniverseGraph(universeId!, {
        depth,
        entity_types: Array.from(enabledTypes),
        limit_per_depth: 100,
      }),
    enabled: !!universeId,
  });

  // ─── React Flow state ────────────────────────────────────
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const [selectedNode, setSelectedNode] = useState<Node | null>(null);

  // Sync React Flow state from query data, with search filter.
  useMemo(() => {
    if (!graphQ.data) {
      setNodes([]);
      setEdges([]);
      return;
    }
    const filtered = filterGraph(graphQ.data, search);
    setNodes(filtered.nodes);
    setEdges(filtered.edges);
  }, [graphQ.data, search, setNodes, setEdges]);

  // Ego-graph mutation: when user clicks a node, swap in just that node's
  // neighborhood at depth 2.
  const egoQ = useQuery({
    queryKey: ["egoGraph", universeId, selectedNode?.id, 2],
    queryFn: () => graphApi.getEgoGraph(universeId!, selectedNode!.id, 2),
    enabled: !!universeId && !!selectedNode,
  });

  const onNodeClick = useCallback((_: unknown, node: Node) => {
    setSelectedNode(node);
  }, []);

  // ─── Multi-select batch delete (T-063) ───────────────────
  const qc = useQueryClient();
  // Selected entity nodes (universe roots excluded — they aren't deletable here).
  const [batchSelection, setBatchSelection] = useState<{ id: string; label: string }[]>([]);
  const onSelectionChange = useCallback(
    ({ nodes: sel }: { nodes: Node[] }) => {
      setBatchSelection(
        sel
          .filter((n) => (n.data as { kind?: string })?.kind !== "universe")
          .map((n) => ({ id: n.id, label: (n.data as { label?: string })?.label ?? n.id })),
      );
    },
    [],
  );

  const batchDelete = useMutation({
    mutationFn: (ids: string[]) => entitiesApi.batchDeleteEntities(ids),
    onSuccess: () => {
      setBatchSelection([]);
      setSelectedNode(null);
      qc.invalidateQueries({ queryKey: ["universeGraph", universeId] });
      graphQ.refetch();
    },
  });

  // ─── Inline relationship drawing (M-37) ───────────────────
  const [pendingEdge, setPendingEdge] = useState<Connection | null>(null);
  const [relType, setRelType] = useState<string>(REL_TYPES[0]);

  const onConnect = useCallback((conn: Connection) => {
    // Don't connect a universe root node; only real entities can relate.
    if (conn.source && conn.target && conn.source !== conn.target) {
      setPendingEdge(conn);
      setRelType(REL_TYPES[0]);
    }
  }, []);

  const createEdge = useMutation({
    mutationFn: ({ from_id, to_id, rel_type }: { from_id: string; to_id: string; rel_type: string }) =>
      entitiesApi.createRelationship({ from_id, to_id, rel_type }),
    onSuccess: (_data, vars) => {
      setEdges((eds) =>
        addEdge(
          { source: vars.from_id, target: vars.to_id, label: vars.rel_type, id: `${vars.from_id}-${vars.rel_type}-${vars.to_id}` },
          eds,
        ),
      );
      setPendingEdge(null);
      qc.invalidateQueries({ queryKey: ["universeGraph", universeId] });
    },
  });

  // ─── Edge context menu: edit / delete (F2-2 phase 4) ───────
  const [edgeMenu, setEdgeMenu] = useState<{ edge: Edge; x: number; y: number } | null>(null);
  const [editingRel, setEditingRel] = useState<{ edge: Edge; rel: EntityRelationship } | null>(null);
  const [edgeActionError, setEdgeActionError] = useState<string | null>(null);
  const [resolvingEdge, setResolvingEdge] = useState(false);

  const onEdgeContextMenu = useCallback((event: ReactMouseEvent, edge: Edge) => {
    event.preventDefault();
    setEdgeActionError(null);
    setEdgeMenu({ edge, x: event.clientX, y: event.clientY });
  }, []);

  // A backend edge id is "rel-<neo4j internal id>"; edges freshly drawn
  // on-canvas (before the graph refetch) carry a synthetic id, so those are
  // resolved by matching endpoints + type against the source node's edges.
  const resolveEdgeRelationship = useCallback(
    async (edge: Edge): Promise<EntityRelationship | null> => {
      const { relationships } = await entitiesApi.listRelationships(edge.source);
      const m = /^rel-(.+)$/.exec(edge.id);
      if (m) {
        const hit = relationships.find((r) => r.relationship_id === m[1]);
        if (hit) return hit;
      }
      const label = String(
        (edge.data as { label?: string } | undefined)?.label ?? edge.label ?? "",
      )
        .toUpperCase()
        .replace(/ /g, "_");
      const candidates = relationships.filter(
        (r) => r.to_entity_id === edge.target && (!label || r.rel_type === label),
      );
      return candidates[0] ?? null;
    },
    [],
  );

  const invalidateGraph = useCallback(() => {
    qc.invalidateQueries({ queryKey: ["universeGraph", universeId] });
    graphQ.refetch();
  }, [qc, universeId, graphQ]);

  const updateEdge = useMutation({
    mutationFn: ({
      relationshipId,
      body,
    }: {
      relationshipId: string;
      body: { category?: string; tags?: string[]; properties?: Record<string, unknown> };
    }) => entitiesApi.updateRelationship(relationshipId, body),
    onSuccess: () => {
      setEditingRel(null);
      invalidateGraph();
    },
  });

  const deleteEdge = useMutation({
    mutationFn: (relationshipId: string) => entitiesApi.deleteRelationship(relationshipId),
    onSuccess: (_data, relationshipId) => {
      setEdges((eds) => eds.filter((e) => e.id !== `rel-${relationshipId}`));
      setEdgeMenu(null);
      invalidateGraph();
    },
  });

  const openEdgeEditor = useCallback(
    async (edge: Edge) => {
      setResolvingEdge(true);
      setEdgeActionError(null);
      try {
        const rel = await resolveEdgeRelationship(edge);
        if (!rel) {
          setEdgeActionError("Could not resolve this edge to a stored relationship.");
          return;
        }
        setEdgeMenu(null);
        setEditingRel({ edge, rel });
      } catch (err) {
        setEdgeActionError((err as Error)?.message ?? "Edge lookup failed");
      } finally {
        setResolvingEdge(false);
      }
    },
    [resolveEdgeRelationship],
  );

  const confirmDeleteEdge = useCallback(
    async (edge: Edge) => {
      setResolvingEdge(true);
      setEdgeActionError(null);
      try {
        const rel = await resolveEdgeRelationship(edge);
        if (!rel) {
          setEdgeActionError("Could not resolve this edge to a stored relationship.");
          return;
        }
        if (
          window.confirm(
            `Delete relationship ${nodeLabel(nodes, rel.from_entity_id)} → ${nodeLabel(nodes, rel.to_entity_id)} (${rel.rel_type})? This cannot be undone.`,
          )
        ) {
          deleteEdge.mutate(rel.relationship_id);
        } else {
          setEdgeMenu(null);
        }
      } catch (err) {
        setEdgeActionError((err as Error)?.message ?? "Edge lookup failed");
      } finally {
        setResolvingEdge(false);
      }
    },
    [resolveEdgeRelationship, deleteEdge, nodes],
  );

  // ─── On-canvas node creation (M-38) ───────────────────────
  const [showAddNode, setShowAddNode] = useState(false);
  const [newName, setNewName] = useState("");
  const [newType, setNewType] = useState<string>(ENTITY_TYPES[0].id);

  const createNode = useMutation({
    mutationFn: () =>
      entitiesApi.createEntity({
        universe_id: universeId!,
        name: newName.trim(),
        entity_type: newType,
      }),
    onSuccess: () => {
      setShowAddNode(false);
      setNewName("");
      qc.invalidateQueries({ queryKey: ["universeGraph", universeId] });
      graphQ.refetch();
    },
  });

  return (
    <div className="min-h-screen flex flex-col">
      {/* Header + filter bar */}
      <header className="border-b border-border bg-bg-card/40 backdrop-blur p-4">
        <div className="max-w-7xl mx-auto flex flex-wrap items-end gap-4">
          <div className="flex items-center gap-3 mr-auto">
            <Compass className="h-5 w-5 text-accent-primary" />
            <div>
              <h1 className="text-lg font-semibold text-fg-primary">Graph Explorer</h1>
              <p className="text-xs text-fg-muted">
                Q-11: drill into a universe to see entities and their relationships
              </p>
            </div>
          </div>

          <div>
            <label className="block text-[10px] text-fg-muted mb-0.5">Multiverse</label>
            <select
              className="select text-sm w-44"
              value={multiverseId ?? ""}
              onChange={(e) => {
                setMultiverseId(e.target.value || null);
                setUniverseId(null);
              }}
            >
              <option value="">— select —</option>
              {(multiversesQ.data ?? []).map((mv: Multiverse) => (
                <option key={mv.id} value={mv.id}>
                  {mv.name}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-[10px] text-fg-muted mb-0.5">Universe</label>
            <select
              className="select text-sm w-56"
              value={universeId ?? ""}
              onChange={(e) => {
                setUniverseId(e.target.value || null);
                setSelectedNode(null);
              }}
              disabled={!multiverseId}
            >
              <option value="">— select —</option>
              {(universesQ.data ?? []).map((u: Universe) => (
                <option key={u.id} value={u.id}>
                  {u.name}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Filter row */}
        <div className="max-w-7xl mx-auto mt-3 flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-1.5 text-xs text-fg-muted">
            <Filter className="h-3.5 w-3.5" /> Entity types:
          </div>
          {ENTITY_TYPES.map((t) => {
            const on = enabledTypes.has(t.id);
            return (
              <button
                key={t.id}
                className={cn(
                  "btn-ghost text-xs py-1 px-2",
                  on && "bg-accent-primary/20 text-accent-primary",
                )}
                onClick={() =>
                  setEnabledTypes((prev) => {
                    const next = new Set(prev);
                    if (next.has(t.id)) next.delete(t.id);
                    else next.add(t.id);
                    return next;
                  })
                }
              >
                {t.label}
              </button>
            );
          })}

          <div className="flex items-center gap-1.5 ml-4 text-xs text-fg-muted">
            Depth:
            <input
              type="range"
              min={1}
              max={5}
              value={depth}
              onChange={(e) => setDepth(Number(e.target.value))}
              className="w-24"
            />
            <span className="font-mono text-fg-primary">{depth}</span>
          </div>

          <div className="ml-auto relative">
            <Search className="h-3.5 w-3.5 text-fg-muted absolute left-2 top-1/2 -translate-y-1/2" />
            <input
              className="input text-sm pl-7 w-56"
              placeholder="Filter nodes…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
            {search && (
              <button
                className="absolute right-1 top-1/2 -translate-y-1/2 p-1 text-fg-muted"
                onClick={() => setSearch("")}
              >
                <X className="h-3 w-3" />
              </button>
            )}
          </div>

          <button
            className="btn-primary"
            onClick={() => { setNewName(""); setShowAddNode(true); }}
            disabled={!universeId}
            title="Add a node to this universe"
          >
            <Plus className="h-4 w-4" /> Add node
          </button>

          <button
            className="btn-secondary"
            onClick={() => graphQ.refetch()}
            disabled={!universeId || graphQ.isFetching}
            title="Refresh"
          >
            <RefreshCw className={cn("h-4 w-4", graphQ.isFetching && "animate-spin")} />
          </button>
        </div>
      </header>

      {/* Graph canvas */}
      <div className="flex-1 relative">
        {!universeId ? (
          <EmptyState
            icon={Network}
            message="Select a universe to explore its entity graph."
          />
        ) : graphQ.isLoading ? (
          <div className="absolute inset-0 flex items-center justify-center text-fg-muted">
            <Loader2 className="h-6 w-6 animate-spin mr-2" /> Loading graph…
          </div>
        ) : graphQ.isError ? (
          <ErrorState message="Could not reach the backend." />
        ) : (graphQ.data?.nodes?.length ?? 0) === 0 ? (
          <EmptyState
            icon={Network}
            message={
              graphQ.data && "error" in graphQ.data && graphQ.data.error
                ? `Backend error: ${graphQ.data.error}`
                : "No entities match the current filters. Try enabling more types or increasing depth."
            }
          />
        ) : (
          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={nodeTypes}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onNodeClick={onNodeClick}
            onConnect={onConnect}
            onEdgeContextMenu={onEdgeContextMenu}
            onSelectionChange={onSelectionChange}
            selectionOnDrag
            multiSelectionKeyCode="Shift"
            fitView
            proOptions={{ hideAttribution: true }}
          >
            <Background variant={BackgroundVariant.Dots} gap={20} size={1} />
            <Controls />
            <MiniMap
              nodeColor={(n) => nodeFillForKind((n.data as { kind?: GraphNodeKind })?.kind)}
              pannable
              zoomable
            />
          </ReactFlow>
        )}
      </div>

      {/* Selected-node / ego-graph side panel */}
      {selectedNode && (
        <NodeDetailPanel
          node={selectedNode}
          egoGraph={egoQ.data ?? null}
          onClose={() => setSelectedNode(null)}
          isLoading={egoQ.isLoading}
        />
      )}

      {/* Multi-select batch action bar (T-063) */}
      {batchSelection.length > 1 && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-40 flex items-center gap-3 rounded-2xl border border-border bg-bg-card/95 backdrop-blur px-4 py-2.5 shadow-2xl">
          <span className="text-xs font-bold text-accent-primary">
            {batchSelection.length} entities selected
          </span>
          <span className="text-[11px] text-fg-muted max-w-xs truncate">
            {batchSelection.map((s) => s.label).join(", ")}
          </span>
          <div className="w-px h-5 bg-border" />
          <button
            onClick={() => {
              if (
                window.confirm(
                  `Permanently delete ${batchSelection.length} entities? This cannot be undone.`,
                )
              ) {
                batchDelete.mutate(batchSelection.map((s) => s.id));
              }
            }}
            disabled={batchDelete.isPending}
            className="flex items-center gap-1.5 text-xs font-bold text-red-300 hover:text-red-200 disabled:opacity-40"
          >
            {batchDelete.isPending ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <Trash2 className="w-3.5 h-3.5" />
            )}
            Delete
          </button>
          <button
            onClick={() => setBatchSelection([])}
            className="text-xs text-fg-muted hover:text-fg"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}
      {batchDelete.isError && (
        <div className="fixed bottom-20 left-1/2 -translate-x-1/2 z-40 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-300">
          Batch delete failed: {(batchDelete.error as Error)?.message}
        </div>
      )}

      {/* Relationship-type picker for a drawn edge (M-37) */}
      {pendingEdge && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
          <div className="w-80 rounded-2xl border border-border bg-bg-card p-4 shadow-2xl">
            <div className="flex items-center gap-2 mb-3">
              <Link2 className="h-4 w-4 text-accent-primary" />
              <h3 className="text-sm font-semibold text-fg-primary">New relationship</h3>
              <button
                className="ml-auto btn-ghost p-1"
                onClick={() => setPendingEdge(null)}
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <p className="text-xs text-fg-muted mb-2">
              {nodeLabel(nodes, pendingEdge.source)} →{" "}
              {nodeLabel(nodes, pendingEdge.target)}
            </p>
            <label className="block text-[10px] text-fg-muted mb-0.5">Type</label>
            <select
              className="select text-sm w-full mb-3"
              value={relType}
              onChange={(e) => setRelType(e.target.value)}
            >
              {REL_TYPES.map((t) => (
                <option key={t} value={t}>
                  {t.replace(/_/g, " ").toLowerCase()}
                </option>
              ))}
            </select>
            {createEdge.isError && (
              <p className="text-[11px] text-red-300 mb-2">
                Could not create: {(createEdge.error as Error)?.message}
              </p>
            )}
            <div className="flex gap-2">
              <button
                className="btn-primary flex-1 justify-center text-sm"
                disabled={createEdge.isPending}
                onClick={() =>
                  createEdge.mutate({
                    from_id: pendingEdge.source!,
                    to_id: pendingEdge.target!,
                    rel_type: relType,
                  })
                }
              >
                {createEdge.isPending ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Link2 className="h-4 w-4" />
                )}
                Connect
              </button>
              <button
                className="btn-ghost flex-1 justify-center text-sm border border-border"
                onClick={() => setPendingEdge(null)}
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
      {/* Add-node form (M-38) */}
      {showAddNode && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
          <div className="w-80 rounded-2xl border border-border bg-bg-card p-4 shadow-2xl">
            <div className="flex items-center gap-2 mb-3">
              <Plus className="h-4 w-4 text-accent-primary" />
              <h3 className="text-sm font-semibold text-fg-primary">Add node</h3>
              <button
                className="ml-auto btn-ghost p-1"
                onClick={() => setShowAddNode(false)}
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <label className="block text-[10px] text-fg-muted mb-0.5">Name</label>
            <input
              autoFocus
              className="input text-sm w-full mb-3"
              placeholder="e.g. The Iron Brotherhood"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && newName.trim()) createNode.mutate();
              }}
            />
            <label className="block text-[10px] text-fg-muted mb-0.5">Type</label>
            <select
              className="select text-sm w-full mb-3"
              value={newType}
              onChange={(e) => setNewType(e.target.value)}
            >
              {ENTITY_TYPES.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.label}
                </option>
              ))}
            </select>
            {createNode.isError && (
              <p className="text-[11px] text-red-300 mb-2">
                Could not create: {(createNode.error as Error)?.message}
              </p>
            )}
            <div className="flex gap-2">
              <button
                className="btn-primary flex-1 justify-center text-sm"
                disabled={createNode.isPending || !newName.trim()}
                onClick={() => createNode.mutate()}
              >
                {createNode.isPending ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Plus className="h-4 w-4" />
                )}
                Create
              </button>
              <button
                className="btn-ghost flex-1 justify-center text-sm border border-border"
                onClick={() => setShowAddNode(false)}
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Edge context menu (F2-2 phase 4) */}
      {edgeMenu && (
        <>
          <div
            className="fixed inset-0 z-40"
            data-testid="edge-menu-backdrop"
            onClick={() => setEdgeMenu(null)}
            onContextMenu={(e) => {
              e.preventDefault();
              setEdgeMenu(null);
            }}
          />
          <div
            role="menu"
            aria-label="Edge actions"
            className="fixed z-50 w-52 rounded-xl border border-border bg-bg-card shadow-2xl py-1"
            style={{ left: edgeMenu.x, top: edgeMenu.y }}
          >
            <p className="px-3 py-1.5 text-[10px] text-fg-muted truncate">
              {String(
                (edgeMenu.edge.data as { label?: string } | undefined)?.label ??
                  edgeMenu.edge.label ??
                  edgeMenu.edge.id,
              )}
            </p>
            <button
              role="menuitem"
              className="w-full flex items-center gap-2 px-3 py-1.5 text-xs text-fg-primary hover:bg-white/5"
              onClick={() => openEdgeEditor(edgeMenu.edge)}
            >
              <Pencil className="w-3.5 h-3.5" /> Edit relationship
            </button>
            <button
              role="menuitem"
              className="w-full flex items-center gap-2 px-3 py-1.5 text-xs text-red-300 hover:bg-red-500/10 disabled:opacity-40"
              disabled={deleteEdge.isPending}
              onClick={() => confirmDeleteEdge(edgeMenu.edge)}
            >
              <Trash2 className="w-3.5 h-3.5" /> Delete relationship
            </button>
          </div>
        </>
      )}

      {resolvingEdge && (
        <div className="fixed bottom-6 right-6 z-40 flex items-center gap-2 rounded-lg border border-border bg-bg-card/95 px-3 py-2 text-xs text-fg-muted shadow-xl">
          <Loader2 className="w-3.5 h-3.5 animate-spin" /> Resolving edge…
        </div>
      )}
      {edgeActionError && (
        <div
          role="alert"
          className="fixed bottom-6 left-1/2 -translate-x-1/2 z-40 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-300"
        >
          {edgeActionError}
        </div>
      )}

      {/* Edge edit modal (F2-2 phase 4) */}
      {editingRel && (
        <EdgeEditModal
          nodes={nodes}
          rel={editingRel.rel}
          isPending={updateEdge.isPending}
          error={updateEdge.isError ? ((updateEdge.error as Error)?.message ?? "Update failed") : null}
          onClose={() => setEditingRel(null)}
          onSave={(body) =>
            updateEdge.mutate({ relationshipId: editingRel.rel.relationship_id, body })
          }
        />
      )}
    </div>
  );
}

/** Edit an existing relationship's category / tags / properties. The
 *  rel_type itself is structural and can't be changed by the update API. */
function EdgeEditModal({
  nodes,
  rel,
  isPending,
  error,
  onClose,
  onSave,
}: {
  nodes: Node[];
  rel: EntityRelationship;
  isPending: boolean;
  error: string | null;
  onClose: () => void;
  onSave: (body: {
    category?: string;
    tags?: string[];
    properties?: Record<string, unknown>;
  }) => void;
}) {
  const [category, setCategory] = useState(rel.category ?? "generic");
  const [tagsText, setTagsText] = useState((rel.tags ?? []).join(", "));
  const [propsText, setPropsText] = useState(
    Object.keys(rel.properties ?? {}).length > 0
      ? JSON.stringify(rel.properties, null, 2)
      : "",
  );
  const [jsonError, setJsonError] = useState<string | null>(null);

  const categories = REL_CATEGORIES.includes(category as (typeof REL_CATEGORIES)[number])
    ? REL_CATEGORIES
    : ([category, ...REL_CATEGORIES] as const);

  const submit = () => {
    let properties: Record<string, unknown> | undefined;
    if (propsText.trim()) {
      try {
        const parsed: unknown = JSON.parse(propsText);
        if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
          setJsonError("Properties must be a JSON object.");
          return;
        }
        properties = parsed as Record<string, unknown>;
      } catch {
        setJsonError("Properties are not valid JSON.");
        return;
      }
    } else {
      properties = {};
    }
    setJsonError(null);
    onSave({
      category,
      tags: tagsText
        .split(",")
        .map((t) => t.trim())
        .filter(Boolean),
      properties,
    });
  };

  return (
    <DialogShell
      title="Edit relationship"
      icon={GitBranch}
      onClose={onClose}
      footer={
        <DialogFooter>
          <button className="btn-ghost text-xs" onClick={onClose} disabled={isPending}>
            Cancel
          </button>
          <button
            className="btn-primary text-xs py-1.5 disabled:opacity-40"
            disabled={isPending}
            onClick={submit}
          >
            {isPending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : null}
            Save changes
          </button>
        </DialogFooter>
      }
    >
      <div className="p-4 space-y-3">
        <p className="text-xs text-fg-muted">
          {nodeLabel(nodes, rel.from_entity_id)} → {nodeLabel(nodes, rel.to_entity_id)}{" "}
          <span className="font-mono text-fg-primary">({rel.rel_type})</span>
        </p>
        <div>
          <label className="block text-[10px] text-fg-muted mb-0.5">Category</label>
          <select
            aria-label="Relationship category"
            className="select text-sm w-full"
            value={category}
            onChange={(e) => setCategory(e.target.value)}
          >
            {categories.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-[10px] text-fg-muted mb-0.5">
            Tags (comma-separated)
          </label>
          <input
            aria-label="Relationship tags"
            className="input text-sm w-full"
            value={tagsText}
            onChange={(e) => setTagsText(e.target.value)}
            placeholder="e.g. secret, political"
          />
        </div>
        <div>
          <label className="block text-[10px] text-fg-muted mb-0.5">
            Properties (JSON object, optional)
          </label>
          <textarea
            aria-label="Relationship properties"
            className="input text-xs font-mono w-full resize-none"
            rows={4}
            value={propsText}
            onChange={(e) => setPropsText(e.target.value)}
            placeholder='{"since": "year 942"}'
          />
        </div>
        {jsonError && <p className="text-[11px] text-red-300">{jsonError}</p>}
        {error && <p className="text-[11px] text-red-300">Save failed: {error}</p>}
      </div>
    </DialogShell>
  );
}

function nodeLabel(nodes: Node[], id: string | null): string {
  if (!id) return "?";
  const n = nodes.find((x) => x.id === id);
  return ((n?.data as { label?: string })?.label ?? id).toString();
}

// ─── Helpers ─────────────────────────────────────────────────

function filterGraph(graph: WorldGraph, search: string): { nodes: Node[]; edges: Edge[] } {
  if (!search.trim()) {
    return {
      nodes: toReactFlowGraph(graph).nodes,
      edges: toReactFlowGraph(graph).edges,
    };
  }
  const q = search.toLowerCase();
  const matchingIds = new Set(
    (graph.nodes ?? [])
      .filter((n: { data?: { label?: string } }) =>
        n.data?.label?.toLowerCase().includes(q),
      )
      .map((n: { id: string }) => n.id),
  );
  return {
    nodes: (graph.nodes ?? [])
      .filter((n) => matchingIds.has(n.id))
      .map(toReactFlowNode),
    edges: (graph.edges ?? [])
      .filter(
        (e) => matchingIds.has(e.source) && matchingIds.has(e.target),
      )
      .map(toReactFlowEdge),
  };
}

function EmptyState({
  icon: Icon,
  message,
}: {
  icon: React.ElementType;
  message: string;
}) {
  return (
    <div className="absolute inset-0 flex flex-col items-center justify-center text-center p-8">
      <Icon className="h-10 w-10 text-fg-dim mb-3" />
      <p className="text-sm text-fg-muted max-w-md">{message}</p>
    </div>
  );
}

function ErrorState({ message }: { message: string }) {
  return (
    <div className="absolute inset-0 flex flex-col items-center justify-center text-center p-8">
      <WifiOff className="h-10 w-10 text-red-400 mb-3" />
      <p className="text-sm text-red-300">{message}</p>
    </div>
  );
}

function NodeDetailPanel({
  node,
  egoGraph,
  onClose,
  isLoading,
}: {
  node: Node;
  egoGraph: WorldGraph | null;
  onClose: () => void;
  isLoading: boolean;
}) {
  const data = (node.data ?? {}) as {
    label?: string;
    kind?: string;
    subtitle?: string;
    tags?: string[];
  };

  return (
    <aside className="absolute top-0 right-0 h-full w-80 bg-bg-card/95 backdrop-blur border-l border-border shadow-xl flex flex-col">
      <header className="flex items-center gap-2 p-3 border-b border-border">
        <h3 className="text-sm font-semibold text-fg-primary flex-1 truncate">
          {data.label ?? node.id}
        </h3>
        <button className="btn-ghost p-1" onClick={onClose} aria-label="Close">
          <X className="h-4 w-4" />
        </button>
      </header>
      <div className="p-3 space-y-3 overflow-y-auto flex-1 text-xs">
        <div>
          <div className="text-fg-muted">Kind</div>
          <div className="text-fg-primary font-mono">{data.kind ?? "—"}</div>
        </div>
        {data.subtitle && (
          <div>
            <div className="text-fg-muted">Subtitle</div>
            <div className="text-fg-primary">{data.subtitle}</div>
          </div>
        )}
        {data.tags && data.tags.length > 0 && (
          <div>
            <div className="text-fg-muted">Tags</div>
            <div className="flex flex-wrap gap-1">
              {data.tags.map((t) => (
                <span
                  key={t}
                  className="text-[10px] px-1.5 py-0.5 rounded bg-white/5 text-fg-muted border border-white/8"
                >
                  {t}
                </span>
              ))}
            </div>
          </div>
        )}
        <div>
          <div className="text-fg-muted mb-1">Ego graph (depth 2)</div>
          {isLoading ? (
            <div className="flex items-center text-fg-muted">
              <Loader2 className="h-3 w-3 animate-spin mr-1" /> Loading…
            </div>
          ) : egoGraph ? (
            <div className="text-fg-primary">
              {egoGraph.nodes?.length ?? 0} node{(egoGraph.nodes?.length ?? 0) === 1 ? "" : "s"},{" "}
              {egoGraph.edges?.length ?? 0} edge{(egoGraph.edges?.length ?? 0) === 1 ? "" : "s"}
              <ul className="mt-1 space-y-0.5">
                {(egoGraph.nodes ?? [])
                  .filter((n: { id: string }) => n.id !== node.id)
                  .slice(0, 8)
                  .map((n: { id: string; data?: { label?: string; kind?: string } }) => (
                    <li key={n.id} className="text-fg-muted truncate">
                      · {truncate(n.data?.label ?? n.id, 28)}{" "}
                      <span className="text-fg-dim">({n.data?.kind ?? "?"})</span>
                    </li>
                  ))}
                {(egoGraph.nodes?.length ?? 0) > 9 && (
                  <li className="text-fg-dim">… and more</li>
                )}
              </ul>
            </div>
          ) : (
            <div className="text-fg-muted">—</div>
          )}
        </div>
      </div>
    </aside>
  );
}
