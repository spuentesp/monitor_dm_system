"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { Bot, Brain, Dices, Heart, Loader2, MapPin, Pencil, Sparkles, Swords, Tag, User, X } from "lucide-react";
import { entitiesApi } from "@/lib/api";
import { cn, formatRelativeTime } from "@/lib/utils";
import { NPCProfileEditor, isProfileMissing } from "./NPCProfileEditor";

export function NPCDetailPanel({ npcId, onClose }: { npcId: string; onClose: () => void }) {
  const [editingProfile, setEditingProfile] = useState(false);
  const { data: npc, isLoading } = useQuery({
    queryKey: ["npc", npcId],
    queryFn: () => entitiesApi.getNPC(npcId),
    enabled: !!npcId,
  });
  // Psychological profile (F2-2 phase 5). 404 = none written yet.
  const profileQ = useQuery({
    queryKey: ["npc-profile", npcId],
    queryFn: () => entitiesApi.getNPCProfile(npcId),
    enabled: !!npcId,
    retry: false,
  });
  const profile = profileQ.data ?? null;

  return (
    <motion.div
      initial={{ x: "100%" }}
      animate={{ x: 0 }}
      exit={{ x: "100%" }}
      transition={{ type: "spring", stiffness: 320, damping: 32 }}
      className="fixed right-0 top-0 h-full w-80 glass border-l border-white/5 flex flex-col z-20 overflow-hidden"
    >
      <div className="flex items-center justify-between px-5 py-4 border-b border-white/5">
        <span className="text-sm font-semibold text-slate-200">
          {isLoading ? "Loading…" : npc?.name ?? "NPC"}
        </span>
        <button onClick={onClose} aria-label="Close" className="text-slate-600 hover:text-slate-200">
          <X className="w-4 h-4" />
        </button>
      </div>

      {isLoading && (
        <div className="flex-1 flex items-center justify-center">
          <Loader2 className="w-6 h-6 text-cyan-400 animate-spin" />
        </div>
      )}

      {npc && (
        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-5">
          <div className="flex items-center gap-4">
            <div className="w-16 h-16 rounded-full bg-purple-500/10 border border-purple-500/25 flex items-center justify-center">
              <User className="w-8 h-8 text-purple-400" />
            </div>
            <div>
              <p className="text-base font-semibold text-slate-100">{npc.name}</p>
              <span className="tag-purple">{npc.entity_type}</span>
            </div>
          </div>

          {npc.description && (
            <p className="text-xs text-slate-400 leading-relaxed">{npc.description}</p>
          )}

          {/* Psychological profile (F2-2 phase 5) */}
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <Brain className="w-3 h-3 text-slate-500" />
              <p className="section-label">Psyche Profile</p>
              <button
                aria-label="Edit NPC profile"
                className="ml-auto p-1 text-slate-500 hover:text-cyan-300 transition-colors"
                onClick={() => setEditingProfile(true)}
              >
                <Pencil className="w-3.5 h-3.5" />
              </button>
            </div>
            {profileQ.isLoading ? (
              <p className="text-xs text-slate-700 italic flex items-center gap-1.5">
                <Loader2 className="w-3 h-3 animate-spin" /> Loading profile…
              </p>
            ) : profile ? (
              <div className="glass-dark rounded-lg p-3 border border-white/5 space-y-1.5 text-xs">
                {profile.speech_style && (
                  <p className="text-slate-400">
                    <span className="text-slate-600">Voice:</span> {profile.speech_style}
                  </p>
                )}
                {profile.current_emotional_state && (
                  <p className="text-slate-400">
                    <span className="text-slate-600">Mood:</span>{" "}
                    {profile.current_emotional_state}
                  </p>
                )}
                {profile.values.length > 0 && (
                  <div className="flex flex-wrap gap-1">
                    {profile.values.slice(0, 6).map((v) => (
                      <span key={v} className="tag-dim">{v}</span>
                    ))}
                  </div>
                )}
                <p className="text-[10px] text-slate-600">
                  {Object.keys(profile.traits).length} traits ·{" "}
                  {profile.triggers.length} triggers · {profile.secrets.length} secrets
                </p>
              </div>
            ) : profileQ.isError && isProfileMissing(profileQ.error) ? (
              <p className="text-xs text-slate-700 italic">
                No psyche profile yet — use the pencil to author one.
              </p>
            ) : profileQ.isError ? (
              <p className="text-xs text-red-300/70 italic">Profile could not be loaded.</p>
            ) : null}
          </div>

          {Object.keys(npc.properties).length > 0 && (
            <div className="space-y-2">
              <p className="section-label">Properties</p>
              {Object.entries(npc.properties).map(([k, v]) => (
                <div key={k} className="flex items-start justify-between gap-2 text-xs">
                  <span className="text-slate-600 capitalize">{k.replace(/_/g, " ")}</span>
                  <span className="font-mono text-slate-300 text-right max-w-[60%] break-all">
                    {typeof v === "object" ? JSON.stringify(v) : String(v)}
                  </span>
                </div>
              ))}
            </div>
          )}

          {Object.keys(npc.stats).length > 0 && (
            <div className="space-y-3">
              <p className="section-label">Stats</p>
              {Object.entries(npc.stats as Record<string, number>).map(([k, v]) => (
                <div key={k} className="space-y-1">
                  <div className="flex items-center justify-between text-xs">
                    <span className="text-slate-500 capitalize">{k}</span>
                    <span className="font-mono text-cyan-300">{v}</span>
                  </div>
                  {typeof v === "number" && v <= 100 && (
                    <div className="stat-bar-track">
                      <div className="stat-bar-fill bg-cyan-500" style={{ width: `${v}%` }} />
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}

          {npc.state_tags.length > 0 && (
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <Tag className="w-3 h-3 text-slate-500" />
                <p className="section-label">State Tags</p>
              </div>
              <div className="flex flex-wrap gap-1.5">
                {npc.state_tags.map((t) => (
                  <span key={t} className="tag-dim">{t}</span>
                ))}
              </div>
            </div>
          )}

          {npc.memories.length > 0 && (
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <Brain className="w-3 h-3 text-slate-500" />
                <p className="section-label">Memories ({npc.memories.length})</p>
              </div>
              <div className="space-y-2">
                {npc.memories.slice(0, 8).map((m) => (
                  <div key={m.id} className="glass-dark rounded-lg p-3 border border-white/5">
                    <p className="text-xs text-slate-300 leading-relaxed">{m.content}</p>
                    <div className="flex items-center justify-between mt-2">
                      <span className="tag-dim">{m.memory_type}</span>
                      <span className="text-[10px] text-slate-600">{formatRelativeTime(m.timestamp)}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {npc.relationships.length > 0 && (
            <div className="space-y-2">
              <p className="section-label">Relationships</p>
              {npc.relationships.slice(0, 6).map((r, i) => (
                <div key={`${String(r.target ?? r.target_name ?? i)}-${String(r.relation_type ?? r.type ?? i)}`} className="flex items-center gap-2 text-xs text-slate-400">
                  <div className="w-1.5 h-1.5 rounded-full bg-purple-500 flex-shrink-0" />
                  <span>{String(r.target_name ?? r.target ?? "Unknown")}</span>
                  <span className="text-slate-600 ml-auto">{String(r.relation_type ?? r.type ?? "")}</span>
                </div>
              ))}
            </div>
          )}

          {npc.facts && npc.facts.length > 0 && (
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <Sparkles className="w-3 h-3 text-slate-500" />
                <p className="section-label">Lore ({npc.facts.length})</p>
              </div>
              <div className="space-y-2">
                {npc.facts.map((f) => (
                  <div key={f.id} className="glass-dark rounded-lg p-3 border border-white/5">
                    <p className="text-xs text-slate-300 leading-relaxed">{f.statement}</p>
                    <div className="flex items-center justify-between mt-1.5">
                      <span className="tag-dim capitalize">{f.fact_type}</span>
                      <span className="text-[10px] text-slate-700">{Math.round(f.confidence * 100)}% conf</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {editingProfile && (
        <NPCProfileEditor
          npcId={npcId}
          npcName={npc?.name}
          onClose={() => setEditingProfile(false)}
        />
      )}
    </motion.div>
  );
}
