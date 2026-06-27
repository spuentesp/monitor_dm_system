"use client";

import { Compass, MapPin, Shield, Users, Sparkles, Brain, Tag, FlaskConical } from "lucide-react";
import type { ReactElement } from "react";

export function GraphLegend() {
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
