"use client";

import { Suspense, useState, useEffect, useCallback } from "react";
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
  type Node,
  type Edge,
  type Connection,
} from "@xyflow/react";
import { toReactFlowNode, toReactFlowEdge, toReactFlowGraph } from "@/features/graph/adapters";
import "@xyflow/react/dist/style.css";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Compass,
  Filter,
  Link2,
  Loader2,
  Network,
  Plus,
  RefreshCw,
  Search,
  Trash2,
  WifiOff,
  X,
} from "lucide-react";
import { entitiesApi, graphApi, universesApi } from "@/lib/api";
import type { Multiverse, Universe, WorldGraph } from "@/lib/types";
import { cn, truncate } from "@/lib/utils";

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

  useEffect(() => {
    if (!multiverseId && multiversesQ.data && multiversesQ.data.length > 0) {
      setMultiverseId(multiversesQ.data[0].id);
    }
  }, [multiverseId, multiversesQ.data]);

  useEffect(() => {
    if (multiverseId && !universeId && universesQ.data && universesQ.data.length > 0) {
      setUniverseId(universesQ.data[0].id);
    }
  }, [multiverseId, universeId, universesQ.data]);

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
  useEffect(() => {
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
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onNodeClick={onNodeClick}
            onConnect={onConnect}
            onSelectionChange={onSelectionChange}
            selectionOnDrag
            multiSelectionKeyCode="Shift"
            fitView
            proOptions={{ hideAttribution: true }}
          >
            <Background variant={BackgroundVariant.Dots} gap={20} size={1} />
            <Controls />
            <MiniMap
              nodeColor={(n) => {
                const kind = (n.data as { kind?: string })?.kind;
                if (kind === "universe") return "#a78bfa";
                if (kind === "character") return "#22d3ee";
                if (kind === "location") return "#fbbf24";
                if (kind === "faction") return "#34d399";
                return "#94a3b8";
              }}
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
    </div>
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
