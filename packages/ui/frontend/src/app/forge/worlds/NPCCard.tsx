"use client";

import { motion } from "framer-motion";
import { ChevronRight, MemoryStick, MapPin, Shield, Sparkles, User, Users } from "lucide-react";
import { cn, truncate } from "@/lib/utils";
import type { NPC } from "@/lib/types";

export function NPCCard({ npc, onClick }: { npc: NPC; onClick: () => void }) {
  const typeConfig: Record<string, { color: string; icon: React.ElementType }> = {
    character: { color: "tag-purple", icon: User },
    npc: { color: "tag-cyan", icon: User },
    creature: { color: "tag-amber", icon: User },
    location: { color: "tag-amber", icon: MapPin },
    faction: { color: "tag-emerald", icon: Shield },
    organization: { color: "tag-emerald", icon: Users },
    concept: { color: "tag-dim", icon: Sparkles },
    object: { color: "tag-dim", icon: MemoryStick },
  };
  const cfg = typeConfig[npc.entity_type?.toLowerCase()] ?? { color: "tag-dim", icon: Sparkles };
  const TypeIcon = cfg.icon;

  return (
    <motion.button
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      whileHover={{ y: -2 }}
      onClick={onClick}
      className="glass w-full text-left rounded-2xl border border-white/5 hover:border-cyan-500/20 hover:shadow-cyan-glow p-5 space-y-3 transition-all duration-200 group"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-full bg-purple-500/10 border border-purple-500/25 flex items-center justify-center flex-shrink-0">
            <TypeIcon className="w-5 h-5 text-purple-400" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-slate-100 group-hover:text-cyan-200 transition-colors">
              {npc.name}
            </h3>
            <span className={cn("text-[10px] capitalize", cfg.color)}>{npc.entity_type}</span>
          </div>
        </div>
        <ChevronRight className="w-4 h-4 text-slate-600 group-hover:text-cyan-400 transition-colors mt-0.5" />
      </div>

      {npc.description && (
        <p className="text-xs text-slate-500 leading-relaxed">
          {truncate(npc.description, 100)}
        </p>
      )}

      {npc.state_tags.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {npc.state_tags.slice(0, 4).map((t) => (
            <span key={t} className="tag-dim">{t}</span>
          ))}
          {npc.state_tags.length > 4 && (
            <span className="tag-dim">+{npc.state_tags.length - 4}</span>
          )}
        </div>
      )}

      <div className="flex items-center justify-between pt-1 border-t border-white/5">
        <div className="flex items-center gap-1.5 text-xs text-slate-600 capitalize">
          <TypeIcon className="w-3 h-3" />
          <span>{npc.entity_type}</span>
        </div>
        <span className={cn("text-[10px]",
          npc.canon_level === "canon" ? "text-cyan-500/60" : "text-slate-600"
        )}>
          {npc.canon_level}
        </span>
      </div>
    </motion.button>
  );
}
