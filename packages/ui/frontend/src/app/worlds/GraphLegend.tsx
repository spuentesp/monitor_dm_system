"use client";

import { KIND_CONFIG } from "@/lib/kind-config";
import type { GraphNodeKind } from "@/lib/types";

const ORDER: GraphNodeKind[] = [
  "multiverse",
  "universe",
  "character",
  "location",
  "faction",
  "concept",
  "axiom",
  "lore",
  "rule",
  "pack",
];

export function GraphLegend() {
  return (
    <div className="glass-dark rounded-xl border border-white/5 p-3 space-y-1.5">
      {ORDER.map((kind) => {
        const cfg = KIND_CONFIG[kind];
        const Icon = cfg.icon;
        return (
          <div key={kind} className="flex items-center gap-2">
            <Icon className={`w-3 h-3 flex-shrink-0 ${cfg.iconColor}`} />
            <span className="text-[10px] text-slate-500">{cfg.label}</span>
          </div>
        );
      })}
    </div>
  );
}