// Adapter helpers between the backend's `WorldGraph` shape and xyflow's
// `Node`/`Edge` types. The backend returns nodes with our `GraphNode` type
// (typed `data: GraphNodeData`); xyflow wants a generic `Record<string,
// unknown>` `data` plus a node `type` discriminator. They are structurally
// compatible but TS narrows the two differently, so the adapter is the
// canonical place to bridge them.

import type { Edge, Node } from "@xyflow/react";
import type { GraphEdge, GraphNode } from "@/lib/types";

/** Convert a backend graph node into an xyflow Node. */
export function toReactFlowNode(n: GraphNode): Node {
  return {
    id: n.id,
    type: n.type,
    position: n.position,
    data: n.data as unknown as Record<string, unknown>,
  };
}

/** Convert a backend graph edge into an xyflow Edge. */
export function toReactFlowEdge(e: GraphEdge): Edge {
  // GraphEdge is a flat record (id/source/target/label/type/...). xyflow's
  // Edge.data is a Record<string, unknown>; we synthesize one carrying the
  // raw fields so renderers can read them via `props.data`.
  const { id, source, target, ...rest } = e;
  return { id, source, target, data: rest as unknown as Record<string, unknown> };
}

/** Bulk convert. */
export function toReactFlowGraph(graph: {
  nodes?: GraphNode[];
  edges?: GraphEdge[];
}): { nodes: Node[]; edges: Edge[] } {
  return {
    nodes: (graph.nodes ?? []).map(toReactFlowNode),
    edges: (graph.edges ?? []).map(toReactFlowEdge),
  };
}
