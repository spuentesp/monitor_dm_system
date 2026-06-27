"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { motion, AnimatePresence } from "framer-motion";
import {
  ReactFlow,
  Background,
  BackgroundVariant,
  Controls,
  useNodesState,
  useEdgesState,
  Handle,
  Position,
  type Node,
  type Edge,
  type NodeProps,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import {
  Compass,
  Globe2,
  Layers,
  Loader2,
  PanelRightClose,
  PanelRightOpen,
  Plus,
  Send,
  Sparkles,
  User,
  MapPin,
  Users,
  Shield,
  Brain,
  Zap,
  Tag,
  X,
} from "lucide-react";
import { chatApi, graphApi, universesApi } from "@/lib/api";
import { ChatList, Composer, useChatSession, type QuickAction } from "@/features/chat";
import type {
  GraphNodeData,
  GraphNodeKind,
  Multiverse,
  Session,
  Universe,
} from "@/lib/types";
import { cn, formatRelativeTime } from "@/lib/utils";
import { ArchitectMessageBubble } from "./ArchitectMessageBubble";
import { toReactFlowGraph } from "@/features/graph/adapters";

// ═══════════════════════════════════════════════════════════════
//  Graph node renderer (mini)
// ═══════════════════════════════════════════════════════════════

const KIND_CONFIG: Record<GraphNodeKind, { border: string; bg: string; icon: React.ElementType; iconColor: string; label: string }> = {
  multiverse: { border: "border-purple-500/40", bg: "bg-purple-500/8",  icon: Layers,  iconColor: "text-purple-400",  label: "Multiverse" },
  universe:   { border: "border-cyan-500/40",   bg: "bg-cyan-500/8",    icon: Globe2,  iconColor: "text-cyan-400",    label: "Universe"   },
  character:  { border: "border-emerald-500/40",bg: "bg-emerald-500/8", icon: User,    iconColor: "text-emerald-400", label: "Character"  },
  location:   { border: "border-amber-500/40",  bg: "bg-amber-500/8",   icon: MapPin,  iconColor: "text-amber-400",   label: "Location"   },
  faction:    { border: "border-red-500/40",    bg: "bg-red-500/8",     icon: Shield,  iconColor: "text-red-400",     label: "Faction"    },
  concept:    { border: "border-violet-500/40", bg: "bg-violet-500/8",  icon: Brain,   iconColor: "text-violet-400",  label: "Concept"    },
  axiom:      { border: "border-slate-500/40",  bg: "bg-slate-500/8",   icon: Zap,     iconColor: "text-slate-400",   label: "Axiom"      },
  lore:       { border: "border-teal-500/40",   bg: "bg-teal-500/8",    icon: Tag,     iconColor: "text-teal-400",    label: "Lore"       },
  rule:       { border: "border-orange-500/40", bg: "bg-orange-500/8",  icon: Brain,   iconColor: "text-orange-400",  label: "Rule"       },
  pack:       { border: "border-pink-500/40",   bg: "bg-pink-500/8",    icon: Users,   iconColor: "text-pink-400",    label: "Pack"       },
};

function WorldNodeMini({ data, selected }: NodeProps) {
  const nodeData = data as GraphNodeData;
  const cfg = KIND_CONFIG[nodeData.kind] ?? KIND_CONFIG.concept;
  const Icon = cfg.icon;
  return (
    <div className={cn("rounded-lg border px-2 py-1.5 min-w-[80px] max-w-[120px] cursor-pointer transition-all", cfg.border, cfg.bg, selected && "ring-1 ring-white/30")}>
      <Handle type="target" position={Position.Top} className="!border-0 !bg-white/20 !w-1.5 !h-1.5" />
      <div className="flex items-center gap-1.5">
        <Icon className={cn("w-3 h-3 flex-shrink-0", cfg.iconColor)} />
        <span className="text-[10px] font-medium text-slate-200 truncate">{nodeData.label}</span>
      </div>
      <Handle type="source" position={Position.Bottom} className="!border-0 !bg-white/20 !w-1.5 !h-1.5" />
    </div>
  );
}

const MINI_NODE_TYPES = { worldNode: WorldNodeMini };

// ═══════════════════════════════════════════════════════════════
//  Mini graph
// ═══════════════════════════════════════════════════════════════

function MiniGraph({
  multiverseId,
  universeId,
  selectedNodeId,
  onSelectNode,
}: {
  multiverseId: string | null;
  universeId: string | null;
  selectedNodeId: string | null;
  onSelectNode: (id: string, data: GraphNodeData) => void;
}) {
  const { data: graph, isLoading } = useQuery({
    queryKey: ["architect-graph", multiverseId, universeId],
    queryFn: () =>
      graphApi.getWorldGraph({
        multiverse_id: multiverseId ?? undefined,
        universe_id: universeId ?? undefined,
      }),
    enabled: Boolean(multiverseId || universeId),
    refetchInterval: 8000,
  });

  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);

  useEffect(() => {
    if (!graph) return;
    const { nodes: rfNodes, edges: rfEdges } = toReactFlowGraph(graph);
    setNodes(rfNodes);
    setEdges(rfEdges);
  }, [graph, setNodes, setEdges]);

  if (!multiverseId && !universeId) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-center px-4 space-y-2">
        <Compass className="w-8 h-8 text-slate-700" />
        <p className="text-xs text-slate-600">Select a multiverse to see the world graph</p>
      </div>
    );
  }
  if (isLoading) {
    return <div className="flex items-center justify-center h-full"><Loader2 className="w-5 h-5 text-slate-600 animate-spin" /></div>;
  }

  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      onNodesChange={onNodesChange}
      onEdgesChange={onEdgesChange}
      nodeTypes={MINI_NODE_TYPES}
      onNodeClick={(_e, node) => onSelectNode(node.id, node.data as GraphNodeData)}
      fitView
      proOptions={{ hideAttribution: true }}
      className="bg-transparent"
    >
      <Background variant={BackgroundVariant.Dots} gap={16} size={0.5} color="rgba(255,255,255,0.04)" />
      <Controls showInteractive={false} className="!bg-black/40 !border-white/10 !rounded-lg overflow-hidden" />
    </ReactFlow>
  );
}

// ═══════════════════════════════════════════════════════════════
//  Element properties panel
// ═══════════════════════════════════════════════════════════════

function ElementPanel({ nodeData, onClose }: { nodeData: GraphNodeData | null; onClose: () => void }) {
  if (!nodeData) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-center px-4 space-y-2">
        <Sparkles className="w-8 h-8 text-slate-700" />
        <p className="text-xs text-slate-600">Click a node to see its properties</p>
      </div>
    );
  }
  const cfg = KIND_CONFIG[nodeData.kind] ?? KIND_CONFIG.concept;
  const Icon = cfg.icon;
  return (
    <div className="p-4 space-y-4 overflow-y-auto h-full">
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-2">
          <div className={cn("w-8 h-8 rounded-lg border flex items-center justify-center flex-shrink-0", cfg.border, cfg.bg)}>
            <Icon className={cn("w-4 h-4", cfg.iconColor)} />
          </div>
          <div>
            <div className="text-[10px] font-bold tracking-widest uppercase text-slate-500">{cfg.label}</div>
            <div className="text-sm font-semibold text-slate-100">{nodeData.label}</div>
          </div>
        </div>
        <button onClick={onClose} aria-label="Close" className="p-1 rounded text-slate-600 hover:text-slate-300 transition-colors">
          <X className="w-3.5 h-3.5" />
        </button>
      </div>
      {nodeData.subtitle && <p className="text-xs text-slate-400 italic">{nodeData.subtitle}</p>}
      {nodeData.description && (
        <div className="space-y-1">
          <div className="text-[10px] font-bold tracking-widest uppercase text-slate-600">Description</div>
          <p className="text-xs text-slate-400 leading-relaxed">{nodeData.description}</p>
        </div>
      )}
      {nodeData.tags && (nodeData.tags as string[]).length > 0 && (
        <div className="space-y-1.5">
          <div className="text-[10px] font-bold tracking-widest uppercase text-slate-600">Tags</div>
          <div className="flex flex-wrap gap-1.5">
            {(nodeData.tags as string[]).map((tag) => (
              <span key={tag} className="px-2 py-0.5 rounded-full bg-white/5 border border-white/10 text-[10px] text-slate-400">{tag}</span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
//  World / Universe selector
// ═══════════════════════════════════════════════════════════════

function WorldSelector({
  multiverseId,
  universeId,
  onMultiverseChange,
  onUniverseChange,
}: {
  multiverseId: string | null;
  universeId: string | null;
  onMultiverseChange: (id: string | null) => void;
  onUniverseChange: (id: string | null) => void;
}) {
  const qc = useQueryClient();
  const { data: multiverses = [] } = useQuery({ queryKey: ["multiverses"], queryFn: universesApi.listMultiverses });
  const { data: universes = [] } = useQuery({
    queryKey: ["universes", multiverseId],
    queryFn: () => universesApi.listUniverses(multiverseId ?? undefined),
    enabled: Boolean(multiverseId),
  });

  const createMv = useMutation({
    mutationFn: (name: string) => universesApi.createMultiverse({ name }),
    onSuccess: (mv) => { qc.invalidateQueries({ queryKey: ["multiverses"] }); onMultiverseChange(mv.id); },
  });
  const createUv = useMutation({
    mutationFn: (name: string) => universesApi.createUniverse({ name, multiverse_id: multiverseId! }),
    onSuccess: (uv) => { qc.invalidateQueries({ queryKey: ["universes", multiverseId] }); onUniverseChange(uv.id); },
  });

  const [newMvName, setNewMvName] = useState("");
  const [newUvName, setNewUvName] = useState("");
  const [showNewMv, setShowNewMv] = useState(false);
  const [showNewUv, setShowNewUv] = useState(false);

  return (
    <div className="flex items-center gap-3 flex-wrap">
      <div className="flex items-center gap-1.5">
        <Layers className="w-3.5 h-3.5 text-purple-400 flex-shrink-0" />
        <select
          value={multiverseId ?? ""}
          onChange={(e) => { onMultiverseChange(e.target.value || null); onUniverseChange(null); }}
          className="input-cyber py-1 text-xs min-w-[140px]"
        >
          <option value="">Select multiverse…</option>
          {multiverses.map((mv) => <option key={mv.id} value={mv.id}>{mv.name}</option>)}
        </select>
        {showNewMv ? (
          <form onSubmit={(e) => { e.preventDefault(); if (newMvName.trim()) { createMv.mutate(newMvName.trim()); setNewMvName(""); setShowNewMv(false); } }} className="flex items-center gap-1">
            <input autoFocus value={newMvName} onChange={(e) => setNewMvName(e.target.value)} placeholder="Multiverse name…" className="input-cyber py-1 text-xs w-36" />
            <button type="submit" aria-label="Create multiverse" className="p-1 text-purple-400 hover:text-purple-300">{createMv.isPending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Plus className="w-3.5 h-3.5" />}</button>
            <button type="button" onClick={() => setShowNewMv(false)} className="p-1 text-slate-600 hover:text-slate-400"><X className="w-3.5 h-3.5" /></button>
          </form>
        ) : (
          <button onClick={() => setShowNewMv(true)} className="p-1 rounded text-slate-600 hover:text-purple-400 transition-colors" title="New multiverse"><Plus className="w-3.5 h-3.5" /></button>
        )}
      </div>

      {multiverseId && (
        <div className="flex items-center gap-1.5">
          <Globe2 className="w-3.5 h-3.5 text-cyan-400 flex-shrink-0" />
          <select
            value={universeId ?? ""}
            onChange={(e) => onUniverseChange(e.target.value || null)}
            className="input-cyber py-1 text-xs min-w-[140px]"
          >
            <option value="">All universes</option>
            {universes.map((uv) => <option key={uv.id} value={uv.id}>{uv.name}</option>)}
          </select>
          {showNewUv ? (
            <form onSubmit={(e) => { e.preventDefault(); if (newUvName.trim()) { createUv.mutate(newUvName.trim()); setNewUvName(""); setShowNewUv(false); } }} className="flex items-center gap-1">
              <input autoFocus value={newUvName} onChange={(e) => setNewUvName(e.target.value)} placeholder="Universe name…" className="input-cyber py-1 text-xs w-36" />
              <button type="submit" aria-label="Create universe" className="p-1 text-cyan-400 hover:text-cyan-300">{createUv.isPending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Plus className="w-3.5 h-3.5" />}</button>
              <button type="button" onClick={() => setShowNewUv(false)} className="p-1 text-slate-600 hover:text-slate-400"><X className="w-3.5 h-3.5" /></button>
            </form>
          ) : (
            <button onClick={() => setShowNewUv(true)} className="p-1 rounded text-slate-600 hover:text-cyan-400 transition-colors" title="New universe"><Plus className="w-3.5 h-3.5" /></button>
          )}
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
//  Page
// ═══════════════════════════════════════════════════════════════

interface WorldCoverage {
  summary: string;
  openQuestions: string[];
  priorityGaps: Array<{ area: string; priority: number; suggestion: string; example_prompt: string }>;
}

const STARTER_PROMPTS = [
  "Create a fantasy universe called Aethoria",
  "Add a faction: the Iron Brotherhood",
  "Create an NPC: Mira, elven scout",
  "Describe the world's magic system",
];

export default function ArchitectPage() {
  const qc = useQueryClient();

  const [multiverseId, setMultiverseId] = useState<string | null>(null);
  const [universeId, setUniverseId] = useState<string | null>(null);
  const [selectedNodeData, setSelectedNodeData] = useState<GraphNodeData | null>(null);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [showRightPanel, setShowRightPanel] = useState(true);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [input, setInput] = useState("");

  const autoInitRef = useRef<string | null>(null);

  const chat = useChatSession({
    sessionId: activeSessionId,
    onTurnSettled: () => {
      qc.invalidateQueries({ queryKey: ["architect-graph", multiverseId, universeId] });
    },
  });

  const { data: multiverses = [] } = useQuery({ queryKey: ["multiverses"], queryFn: universesApi.listMultiverses });

  const { data: sessions = [], isLoading: sessionsLoading } = useQuery({
    queryKey: ["architect-sessions"],
    queryFn: () => chatApi.listSessions().then((s) => s.filter((x) => x.mode === "world_architect")),
  });

  // Auto-select first multiverse on load
  useEffect(() => {
    if (!multiverseId && multiverses.length > 0) {
      setMultiverseId(multiverses[0].id);
    }
  }, [multiverses]); // eslint-disable-line react-hooks/exhaustive-deps

  const createSession = useMutation({
    mutationFn: () => chatApi.createSession({ title: "World Architect session", mode: "world_architect", multiverse_id: multiverseId, universe_id: universeId }),
    onSuccess: (session) => {
      qc.invalidateQueries({ queryKey: ["architect-sessions"] });
      setActiveSessionId(session.id);
    },
  });

  // Auto-init session when multiverse is selected
  useEffect(() => {
    if (!multiverseId || sessionsLoading) return;
    if (autoInitRef.current === multiverseId) return;
    autoInitRef.current = multiverseId;
    const existing = sessions.find((s) => s.multiverse_id === multiverseId);
    if (existing) {
      setActiveSessionId(existing.id);
    } else {
      createSession.mutate();
    }
  }, [multiverseId, sessions, sessionsLoading]); // eslint-disable-line react-hooks/exhaustive-deps

  // Derive world-coverage state from the most recent GM message metadata.
  // Replaces the setState that used to live inside the WS handler.
  const worldCoverage = useMemo<WorldCoverage | null>(() => {
    for (let i = chat.messages.length - 1; i >= 0; i--) {
      const m = chat.messages[i];
      if (m.role !== "gm") continue;
      const meta = (m.metadata ?? {}) as Record<string, unknown>;
      if (
        meta.coverage_summary ||
        (Array.isArray(meta.known_open_questions) && (meta.known_open_questions as unknown[]).length > 0) ||
        (Array.isArray(meta.priority_gaps) && (meta.priority_gaps as unknown[]).length > 0)
      ) {
        return {
          summary: (meta.coverage_summary as string) ?? "",
          openQuestions: (meta.known_open_questions as string[]) ?? [],
          priorityGaps:
            (meta.priority_gaps as WorldCoverage["priorityGaps"]) ?? [],
        };
      }
    }
    return null;
  }, [chat.messages]);

  const starterActions: QuickAction[] = STARTER_PROMPTS.map((p) => ({
    label: p,
    onClick: "fill",
    text: p,
    disabled: chat.isTyping || !!chat.streamingMsg,
    className: "bg-purple-500/8 border border-purple-500/20 text-purple-300 hover:bg-purple-500/15 px-3 py-1.5",
  }));

  const handleNodeSelect = (id: string, data: GraphNodeData) => {
    setSelectedNodeId(id);
    setSelectedNodeData(data);
    if (!showRightPanel) setShowRightPanel(true);
  };

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Header */}
      <div className="flex items-center gap-4 px-6 py-3 border-b border-white/5 glass-dark flex-shrink-0 flex-wrap">
        <Compass className="w-5 h-5 text-purple-400 flex-shrink-0" />
        <h1 className="text-sm font-bold text-slate-200">World Architect</h1>
        <div className="h-5 w-px bg-white/10" />
        <WorldSelector
          multiverseId={multiverseId}
          universeId={universeId}
          onMultiverseChange={(id) => { autoInitRef.current = null; setMultiverseId(id); setActiveSessionId(null); }}
          onUniverseChange={setUniverseId}
        />
        <div className="ml-auto">
          <button onClick={() => setShowRightPanel((p) => !p)} className="p-1.5 rounded text-slate-500 hover:text-slate-200 transition-colors" title={showRightPanel ? "Hide world panel" : "Show world panel"}>
            {showRightPanel ? <PanelRightClose className="w-4 h-4" /> : <PanelRightOpen className="w-4 h-4" />}
          </button>
        </div>
      </div>

      {/* Body */}
      <div className="flex flex-1 overflow-hidden">
        {/* Sessions (left) */}
        <div className="w-52 flex-shrink-0 glass border-r border-white/5 flex flex-col overflow-hidden">
          <div className="flex items-center justify-between px-3 py-3 border-b border-white/5">
            <span className="text-[10px] font-bold tracking-widest uppercase text-slate-600">Sessions</span>
            <button
              onClick={() => { if (multiverseId) createSession.mutate(); }}
              disabled={!multiverseId || createSession.isPending}
              className="p-1 rounded border border-purple-500/25 text-purple-400 hover:bg-purple-500/10 transition-all disabled:opacity-40"
              title={multiverseId ? "New session" : "Select a multiverse first"}
            >
              {createSession.isPending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Plus className="w-3.5 h-3.5" />}
            </button>
          </div>

          {!multiverseId ? (
            <div className="flex-1 flex flex-col items-center justify-center px-3 text-center space-y-2">
              <Compass className="w-8 h-8 text-slate-700" />
              <p className="text-xs text-slate-600">Select or create a multiverse to begin</p>
            </div>
          ) : sessions.length === 0 ? (
            <div className="flex-1 flex flex-col items-center justify-center px-3 text-center space-y-2">
              <p className="text-xs text-slate-600">No sessions yet.</p>
              <button onClick={() => createSession.mutate()} className="btn-ghost text-xs px-3 py-1"><Plus className="w-3 h-3" /> New session</button>
            </div>
          ) : (
            <div className="flex-1 overflow-y-auto py-1.5 px-2 space-y-1">
              {sessions.map((s: Session) => (
                <button
                  key={s.id}
                  onClick={() => setActiveSessionId(s.id)}
                  className={cn("w-full text-left px-2.5 py-2 rounded-lg text-xs transition-all border", activeSessionId === s.id ? "bg-purple-500/10 border-purple-500/25 text-slate-200" : "border-transparent text-slate-500 hover:text-slate-300 hover:bg-white/4")}
                >
                  <div className="font-medium truncate">{s.title}</div>
                  <div className="text-[10px] text-slate-700 mt-0.5">{formatRelativeTime(s.updated_at)}</div>
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Chat (center) */}
        <div className="flex-1 flex flex-col overflow-hidden">
          {!activeSessionId ? (
            <div className="flex-1 flex flex-col items-center justify-center text-center space-y-4 px-8">
              <div className="w-16 h-16 rounded-2xl bg-purple-500/8 border border-purple-500/15 flex items-center justify-center">
                <Compass className="w-8 h-8 text-purple-500/60" />
              </div>
              <div>
                <h2 className="text-lg font-bold text-slate-300">World Architect</h2>
                <p className="text-sm text-slate-600 mt-1 max-w-sm">
                  Select a multiverse and start a session. Describe what to build — universes, factions, NPCs — and the Architect adds them to your graph.
                </p>
              </div>
              {multiverseId && (
                <button onClick={() => createSession.mutate()} disabled={createSession.isPending} className="btn-cyber">
                  {createSession.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />}
                  Start Building
                </button>
              )}
            </div>
          ) : (
            <>
              <ChatList
                messages={chat.messages}
                streamingMsg={chat.streamingMsg}
                isTyping={chat.isTyping}
                sendFailure={chat.sendFailure}
                pendingDiceRequest={null}
                renderBubble={(msg) => <ArchitectMessageBubble msg={msg} />}
                onDiceResult={() => {
                  /* architect doesn't use dice */
                }}
                onRetry={chat.retry}
                onDismissFailure={chat.dismissFailure}
                emptyState={
                  chat.messages.length === 0 && !chat.isTyping && !chat.streamingMsg ? (
                    <div className="h-full flex flex-col items-center justify-center text-center space-y-3 px-8">
                      <Compass className="w-10 h-10 text-slate-700 mx-auto" />
                      <p className="text-sm text-slate-600">Tell the Architect what to build.</p>
                      <div className="flex flex-wrap gap-2 justify-center mt-3">
                        {starterActions.map((a, i) => (
                          <button
                            key={`${a.label}-${i}`}
                            onClick={() => a.onClick === "fill" ? setInput(a.text) : chat.send(a.text)}
                            className="px-3 py-1.5 rounded-lg text-xs bg-purple-500/8 border border-purple-500/20 text-purple-300 hover:bg-purple-500/15 transition-colors"
                          >
                            {a.label}
                          </button>
                        ))}
                      </div>
                    </div>
                  ) : undefined
                }
              />

              <Composer
                value={input}
                onChange={setInput}
                onSubmit={(text) => chat.send(text)}
                status={chat.status}
                isTyping={chat.isTyping}
                placeholder="Describe what to add to the world… (Enter to send)"
              />
            </>
          )}
        </div>

        {/* Right panel: graph + properties */}
        <AnimatePresence>
          {showRightPanel && (
            <motion.div
              initial={{ width: 0, opacity: 0 }}
              animate={{ width: 360, opacity: 1 }}
              exit={{ width: 0, opacity: 0 }}
              transition={{ type: "spring", stiffness: 300, damping: 30 }}
              className="flex-shrink-0 glass border-l border-white/5 flex flex-col overflow-hidden"
            >
              <div className="flex-1 border-b border-white/5 min-h-0">
                <div className="px-3 py-2 border-b border-white/5 flex-shrink-0">
                  <span className="text-[10px] font-bold tracking-widest uppercase text-slate-600">World Graph</span>
                </div>
                <div className="h-[calc(100%-32px)]">
                  <MiniGraph multiverseId={multiverseId} universeId={universeId} selectedNodeId={selectedNodeId} onSelectNode={handleNodeSelect} />
                </div>
              </div>

              <div className="h-56 flex-shrink-0 overflow-hidden border-b border-white/5">
                <div className="px-3 py-2 border-b border-white/5 flex-shrink-0">
                  <span className="text-[10px] font-bold tracking-widest uppercase text-slate-600">Properties</span>
                </div>
                <div className="h-[calc(100%-32px)] overflow-y-auto">
                  <ElementPanel nodeData={selectedNodeData} onClose={() => { setSelectedNodeData(null); setSelectedNodeId(null); }} />
                </div>
              </div>

              {/* World Coverage Panel */}
              <div className="flex-1 overflow-hidden flex flex-col min-h-0">
                <div className="px-3 py-2 border-b border-white/5 flex-shrink-0 flex items-center gap-2">
                  <span className="text-[10px] font-bold tracking-widest uppercase text-slate-600">World Coverage</span>
                  {worldCoverage && <span className="text-[10px] text-purple-500/60">{worldCoverage.openQuestions.length} open</span>}
                </div>
                <div className="flex-1 overflow-y-auto p-3 space-y-3">
                  {!worldCoverage ? (
                    <p className="text-[10px] text-slate-700 text-center py-4">Coverage updates after each turn.</p>
                  ) : (
                    <>
                      {worldCoverage.summary && (
                        <p className="text-[10px] text-slate-500 leading-relaxed">{worldCoverage.summary}</p>
                      )}
                      {worldCoverage.priorityGaps.length > 0 && (
                        <div className="space-y-1.5">
                          <p className="text-[10px] font-semibold text-slate-600 uppercase tracking-wide">Priority Gaps</p>
                          {worldCoverage.priorityGaps.map((gap, i) => (
                            <div key={i} className="rounded-lg bg-purple-500/5 border border-purple-500/10 px-2.5 py-2 space-y-0.5">
                              <p className="text-[10px] font-medium text-purple-300">{gap.area}</p>
                              <p className="text-[10px] text-slate-500 leading-snug">{gap.suggestion}</p>
                              {gap.example_prompt && (
                                <p className="text-[10px] text-slate-700 italic">"{gap.example_prompt}"</p>
                              )}
                            </div>
                          ))}
                        </div>
                      )}
                      {worldCoverage.openQuestions.length > 0 && (
                        <div className="space-y-1">
                          <p className="text-[10px] font-semibold text-slate-600 uppercase tracking-wide">Open Questions</p>
                          {worldCoverage.openQuestions.map((q, i) => (
                            <p key={i} className="text-[10px] text-slate-600 flex gap-1.5">
                              <span className="text-purple-700 shrink-0">?</span>
                              {q}
                            </p>
                          ))}
                        </div>
                      )}
                    </>
                  )}
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}