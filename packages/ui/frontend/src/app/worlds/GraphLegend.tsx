"use client";

import { Brain, Compass, FlaskConical, MapPin, Shield, Sparkles, Tag, Users } from "lucide-react";

const LEGEND: Array<{ kind: string; label: string; iconColor: string; Icon: React.ElementType }> = [
  { kind: "multiverse", label: "Multiverse",   iconColor: "text-purple-400",  Icon: Compass },
  { kind: "universe",   label: "Universe",     iconColor: "text-cyan-400",    Icon: MapPin },
  { kind: "character",  label: "Character",    iconColor: "text-emerald-400", Icon: Users },
  { kind: "location",   label: "Location",     iconColor: "text-amber-400",   Icon: MapPin },
  { kind: "faction",    label: "Faction",      iconColor: "text-red-400",     Icon: Shield },
  { kind: "concept",    label: "Concept",      iconColor: "text-violet-400",  Icon: Brain },
  { kind: "axiom",      label: "Axiom",        iconColor: "text-slate-400",   Icon: Sparkles },
  { kind: "lore",       label: "Lore",         iconColor: "text-teal-400",    Icon: Tag },
  { kind: "rule",       label: "Rule",         iconColor: "text-orange-400",  Icon: FlaskConical },
];

export function GraphLegend() {
  return (
    <div className="glass-dark rounded-xl border border-white/5 p-3 space-y-1.5">
      {LEGEND.map(({ kind, label, iconColor, Icon }) => (
        <div key={kind} className="flex items-center gap-2">
          <Icon className={`w-3 h-3 flex-shrink-0 ${iconColor}`} />
          <span className="text-[10px] text-slate-500">{label}</span>
        </div>
      ))}
    </div>
  );
}
