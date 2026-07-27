import {
  Brain,
  Globe2,
  Layers,
  MapPin,
  Shield,
  Sparkles,
  Tag,
  User,
  Zap,
} from "lucide-react";
import type { GraphNodeKind } from "@/lib/types";

/**
 * Single source of truth for node-kind chrome. The values here are what
 * users actually see in the world-graph canvas (GraphCanvas.tsx) — all
 * other surfaces (inspector panel, architect mini-graph, graph legend)
 * must import from this module rather than redefine the styles.
 *
 * Previously this constant was duplicated three times with silently
 * divergent values, so e.g. the inspector showed `Shield` for `rule`
 * while the graph showed `Zap`, and the legend showed `FlaskConical`
 * for `rule`. All three renderings now agree.
 */
export const KIND_CONFIG: Record<
  GraphNodeKind,
  {
    border: string;
    bg: string;
    icon: React.ElementType;
    iconColor: string;
    /** Tailwind classes for the small text badge used in the inspector. */
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
    icon: Tag,
    iconColor: "text-teal-400",
    tagClass: "tag-cyan",
    label: "Pack",
  },
};