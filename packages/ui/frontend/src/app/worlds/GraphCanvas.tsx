"use client";

import { memo, useCallback, useEffect } from "react";
import {
  ReactFlow,
  Background,
  BackgroundVariant,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  Handle,
  Position,
  type Node,
  type Edge,
  type NodeProps,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { Brain, Globe2, Layers, MapPin, Shield, Sparkles, User, Zap } from "lucide-react";
import type { GraphNodeData, GraphNodeKind } from "@/lib/types";
import { cn } from "@/lib/utils";

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

export function GraphCanvas({
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
