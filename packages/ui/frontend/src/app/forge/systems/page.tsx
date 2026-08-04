"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  BookOpen,
  ChevronRight,
  Dices,
  Layers,
  Loader2,
  RotateCcw,
  Shield,
  Swords,
  Trash2,
  User,
  Users,
  Zap,
  ListChecks,
  Dice1,
  Star,
} from "lucide-react";
import { entitiesApi } from "@/lib/api";
import type { Character, RPGSystem, RuleInfo, AttributeInfo, SkillInfo, ResourceInfo } from "@/lib/types";
import { cn, truncate } from "@/lib/utils";
import { ENTITY_KEYS } from "@/lib/query-keys";
import { useSystems, useSystem } from "@/hooks/use-systems";

// ─── Rule type badge colors ───────────────────────────────── 

const RULE_TYPE_COLORS: Record<string, string> = {
  combat: "tag-red",
  advancement: "tag-emerald",
  social: "tag-purple",
  exploration: "tag-amber",
  core: "tag-cyan",
  custom: "tag-dim",
};

// ─── System list item ─────────────────────────────────────── 

function SystemItem({
  system,
  active,
  onClick,
  onDelete,
}: {
  system: RPGSystem;
  active: boolean;
  onClick: () => void;
  onDelete: (id: string) => void;
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "w-full text-left px-4 py-4 border-b border-white/5 last:border-0 transition-all group",
        active
          ? "bg-cyan-500/8 border-l-2 border-l-cyan-500"
          : "hover:bg-white/3 border-l-2 border-l-transparent",
      )}
    >
      <div className="flex items-center gap-3">
        <div
          className={cn(
            "w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0",
            active ? "bg-cyan-500/15 border border-cyan-500/30" : "bg-white/5 border border-white/8",
          )}
        >
          <BookOpen className={cn("w-4 h-4", active ? "text-cyan-400" : "text-slate-500")} />
        </div>
        <div className="flex-1 min-w-0">
          <p className={cn("text-sm font-medium truncate", active ? "text-cyan-200" : "text-slate-300")}>
            {system.name}
          </p>
          <div className="flex items-center gap-2 mt-0.5 flex-wrap">
            {system.version && (
              <span className="text-[10px] text-slate-600 whitespace-nowrap">{system.version}</span>
            )}
            {system.is_builtin && (
              <span className="text-[10px] tag-amber whitespace-nowrap">built-in</span>
            )}
            {system.needs_review && (
              <span className="text-[10px] tag-red whitespace-nowrap" title={system.degenerate_reason ?? undefined}>
                needs review
              </span>
            )}
            <span className="text-[10px] text-slate-700 whitespace-nowrap">
              {system.attributes.length} attrs · {system.rules.length} rules
            </span>
          </div>
        </div>
        <div className="flex items-center gap-1">
          {!system.is_builtin && (
            <span
              role="button"
              onClick={(e) => { e.stopPropagation(); if (window.confirm(`Delete "${system.name}"?`)) onDelete(system.id); }}
              className="p-1 rounded text-slate-700 hover:text-red-400 transition-colors opacity-0 group-hover:opacity-100"
              title="Delete system"
            >
              <Trash2 className="w-3 h-3" />
            </span>
          )}
          <ChevronRight className={cn("w-3.5 h-3.5 flex-shrink-0 transition-colors",
            active ? "text-cyan-400" : "text-slate-700")} />
        </div>
      </div>
    </button>
  );
}

// ─── System overview tab ──────────────────────────────────── 

function SystemOverview({ system }: { system: RPGSystem }) {
  return (
    <div className="space-y-4">
      {/* Header card */}
      <div className="glass rounded-2xl border border-white/5 p-5 space-y-4">
        <div className="flex items-start gap-4">
          <div className="w-14 h-14 rounded-2xl bg-purple-500/10 border border-purple-500/25 flex items-center justify-center flex-shrink-0">
            <BookOpen className="w-7 h-7 text-purple-400" />
          </div>
          <div className="flex-1">
            <h2 className="text-lg font-bold text-slate-100">{system.name}</h2>
            <div className="flex items-center gap-2 mt-1 flex-wrap">
              {system.version && <span className="tag-dim">{system.version}</span>}
              {system.is_builtin && <span className="tag-amber">Built-in</span>}
              {system.core_mechanic && (
                <span className="tag-cyan capitalize">
                  {system.core_mechanic.mechanic_type.replace(/_/g, " ")}
                </span>
              )}
              {system.needs_review && <span className="tag-red">Needs review</span>}
            </div>
          </div>
        </div>
        {system.description && (
          <p className="text-sm text-slate-400 leading-relaxed">{system.description}</p>
        )}
        {system.needs_review && system.degenerate_reason && (
          <div className="glass-dark rounded-xl p-3 border border-red-500/20">
            <p className="text-[10px] text-red-400 uppercase tracking-wider mb-1">
              Extraction incomplete
            </p>
            <p className="text-xs text-slate-400">{system.degenerate_reason}</p>
          </div>
        )}
      </div>

      {/* Core mechanic */}
      {system.core_mechanic && (
        <div className="glass rounded-2xl border border-white/5 p-5 space-y-3">
          <div className="flex items-center gap-2">
            <Dice1 className="w-4 h-4 text-slate-500" />
            <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Core Mechanic</h3>
          </div>
          <div className="grid grid-cols-2 gap-3 text-sm">
            <div className="glass-dark rounded-xl p-3">
              <p className="text-[10px] text-slate-600 uppercase tracking-wider mb-1">Type</p>
              <p className="text-slate-200 capitalize">{system.core_mechanic.mechanic_type.replace(/_/g, " ")}</p>
            </div>
            {system.core_mechanic.formula && (
              <div className="glass-dark rounded-xl p-3">
                <p className="text-[10px] text-slate-600 uppercase tracking-wider mb-1">Formula</p>
                <p className="text-slate-200 font-mono text-xs">{system.core_mechanic.formula}</p>
              </div>
            )}
            {system.core_mechanic.success_type && (
              <div className="glass-dark rounded-xl p-3">
                <p className="text-[10px] text-slate-600 uppercase tracking-wider mb-1">Success</p>
                <p className="text-slate-200 capitalize">{system.core_mechanic.success_type.replace(/_/g, " ")}</p>
              </div>
            )}
            {system.core_mechanic.target_number != null && (
              <div className="glass-dark rounded-xl p-3">
                <p className="text-[10px] text-slate-600 uppercase tracking-wider mb-1">Target</p>
                <p className="text-slate-200 font-mono">{system.core_mechanic.target_number}</p>
              </div>
            )}
          </div>
          {system.core_mechanic.description && (
            <p className="text-xs text-slate-500 leading-relaxed">{system.core_mechanic.description}</p>
          )}
        </div>
      )}

      {/* Stats summary */}
      <div className="grid grid-cols-4 gap-3">
        {[
          { label: "Attributes", count: system.attributes.length, color: "text-cyan-300" },
          { label: "Skills", count: system.skills.length, color: "text-purple-300" },
          { label: "Resources", count: system.resources.length, color: "text-emerald-300" },
          { label: "Rules", count: system.rules.length, color: "text-amber-300" },
        ].map(({ label, count, color }) => (
          <div key={label} className="glass-dark rounded-xl p-3 text-center">
            <p className={cn("text-2xl font-bold font-mono", color)}>{count}</p>
            <p className="text-[10px] text-slate-600 mt-0.5">{label}</p>
          </div>
        ))}
      </div>

      {/* How to use */}
      <div className="glass rounded-2xl border border-white/5 p-5 space-y-3">
        <div className="flex items-center gap-2">
          <Swords className="w-4 h-4 text-slate-500" />
          <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider">How to use this system</h3>
        </div>
        <ol className="space-y-2 text-xs text-slate-400">
          <li className="flex gap-2"><span className="text-slate-600 font-mono">1.</span> Go to <strong className="text-slate-300">Play</strong> and start a new session. Select this system in the setup panel.</li>
          <li className="flex gap-2"><span className="text-slate-600 font-mono">2.</span> The GM will walk you through character creation using the attributes and rules defined here.</li>
          <li className="flex gap-2"><span className="text-slate-600 font-mono">3.</span> Use the <strong className="text-slate-300">Test Roll</strong> tab below to preview a randomly generated character sheet.</li>
        </ol>
        <div className="flex items-center gap-4 pt-1">
          <div className="text-center">
            <p className="text-lg font-bold font-mono text-cyan-300">{system.character_count}</p>
            <p className="text-[10px] text-slate-600">Characters</p>
          </div>
          <div className="text-center">
            <p className="text-lg font-bold font-mono text-purple-300">{system.session_count}</p>
            <p className="text-[10px] text-slate-600">Sessions played</p>
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── Attributes & Skills tab ──────────────────────────────── 

function AttributesPanel({ system }: { system: RPGSystem }) {
  if (system.attributes.length === 0 && system.skills.length === 0 && system.resources.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 space-y-2">
        <Shield className="w-10 h-10 text-slate-700" />
        <p className="text-sm text-slate-600">No attributes or skills defined for this system.</p>
      </div>
    );
  }
  return (
    <div className="space-y-5">
      {/* Attributes */}
      {system.attributes.length > 0 && (
        <div className="space-y-3">
          <div className="flex items-center gap-2">
            <Shield className="w-4 h-4 text-slate-500" />
            <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Attributes</h3>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
            {system.attributes.map((attr: AttributeInfo) => (
              <div key={attr.name} className="glass-dark rounded-xl p-3 space-y-1">
                <div className="flex items-center justify-between">
                  <p className="text-sm font-semibold text-slate-200">{attr.name}</p>
                  {attr.abbreviation && (
                    <span className="text-[10px] font-mono text-cyan-400 bg-cyan-500/10 px-1.5 py-0.5 rounded">
                      {attr.abbreviation}
                    </span>
                  )}
                </div>
                {(attr.min_value != null || attr.max_value != null) && (
                  <p className="text-[10px] text-slate-600">
                    Range: {attr.min_value ?? "?"} – {attr.max_value ?? "?"}
                  </p>
                )}
                {attr.description && (
                  <p className="text-[10px] text-slate-600 leading-relaxed">{truncate(attr.description, 80)}</p>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Resources */}
      {system.resources.length > 0 && (
        <div className="space-y-3">
          <div className="flex items-center gap-2">
            <Zap className="w-4 h-4 text-slate-500" />
            <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Resources</h3>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
            {system.resources.map((res: ResourceInfo) => (
              <div key={res.name} className="glass-dark rounded-xl p-3 space-y-1">
                <div className="flex items-center justify-between">
                  <p className="text-sm font-semibold text-slate-200">{res.name}</p>
                  {res.abbreviation && (
                    <span className="text-[10px] font-mono text-emerald-400 bg-emerald-500/10 px-1.5 py-0.5 rounded">
                      {res.abbreviation}
                    </span>
                  )}
                </div>
                {res.max_value != null && (
                  <p className="text-[10px] text-slate-600">Max: {res.max_value}</p>
                )}
                {res.recovers_on && (
                  <p className="text-[10px] text-slate-600">Recovers on: {res.recovers_on}</p>
                )}
                {res.depleted_effect && (
                  <p className="text-[10px] text-red-500/70 leading-relaxed">{truncate(res.depleted_effect, 60)}</p>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Skills */}
      {system.skills.length > 0 && (
        <div className="space-y-3">
          <div className="flex items-center gap-2">
            <Star className="w-4 h-4 text-slate-500" />
            <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Skills</h3>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
            {system.skills.map((skill: SkillInfo) => (
              <div key={skill.name} className="glass-dark rounded-xl px-4 py-3 flex items-start gap-3">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <p className="text-sm font-medium text-slate-200">{skill.name}</p>
                    {skill.linked_attribute && (
                      <span className="text-[10px] tag-dim">{skill.linked_attribute}</span>
                    )}
                    {!skill.untrained_allowed && (
                      <span className="text-[10px] tag-red">trained only</span>
                    )}
                  </div>
                  {skill.description && (
                    <p className="text-[10px] text-slate-600 mt-0.5 leading-relaxed">
                      {truncate(skill.description, 100)}
                    </p>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Rules tab ────────────────────────────────────────────── 

function RulesPanel({ system }: { system: RPGSystem }) {
  if (system.rules.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 space-y-2">
        <ListChecks className="w-10 h-10 text-slate-700" />
        <p className="text-sm text-slate-600">No rules extracted for this system yet.</p>
      </div>
    );
  }
  return (
    <div className="space-y-3">
      {system.rules.map((rule: RuleInfo, i) => (
        <motion.div
          key={rule.name + i}
          initial={{ opacity: 0, y: 4 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: i * 0.03 }}
          className="glass-dark rounded-xl border border-white/5 p-4 space-y-2"
        >
          <div className="flex items-start gap-3">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <p className="text-sm font-semibold text-slate-200">{rule.name}</p>
                <span className={cn("text-[10px]", RULE_TYPE_COLORS[rule.rule_type] ?? "tag-dim")}>
                  {rule.rule_type}
                </span>
              </div>
              {rule.description && (
                <p className="text-xs text-slate-400 mt-1 leading-relaxed">{rule.description}</p>
              )}
            </div>
          </div>
          {rule.formula && (
            <div className="bg-black/20 rounded-lg px-3 py-2">
              <p className="text-[10px] text-slate-600 mb-0.5">Formula</p>
              <p className="text-xs font-mono text-cyan-300">{rule.formula}</p>
            </div>
          )}
          {rule.examples.length > 0 && (
            <div>
              <p className="text-[10px] text-slate-600 mb-1">Examples</p>
              <ul className="space-y-0.5">
                {rule.examples.slice(0, 3).map((ex, j) => (
                  <li key={j} className="text-[10px] text-slate-500 pl-2 border-l border-white/10">
                    {ex}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </motion.div>
      ))}
    </div>
  );
}

// ─── Character stat card ──────────────────────────────────── 

function CharacterCard({ char }: { char: Character }) {
  const attrs = char.attributes as Record<string, number | string>;
  const numericAttrs = Object.entries(attrs).filter(
    ([, v]) => typeof v === "number",
  ) as [string, number][];
  const max = Math.max(...numericAttrs.map(([, v]) => v), 1);

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      className="glass rounded-xl border border-white/5 hover:border-purple-500/25 p-4 space-y-3 transition-all"
    >
      <div className="flex items-center gap-3">
        <div className="w-9 h-9 rounded-full bg-purple-500/10 border border-purple-500/25 flex items-center justify-center flex-shrink-0">
          <User className="w-4 h-4 text-purple-400" />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold text-slate-100 truncate">{char.name}</p>
          {char.description && (
            <p className="text-xs text-slate-600 truncate">{truncate(char.description, 50)}</p>
          )}
        </div>
        <span className={cn("text-[10px] flex-shrink-0",
          char.canon_level === "canon" ? "text-cyan-500/60" : "text-slate-600"
        )}>
          {char.canon_level}
        </span>
      </div>

      {numericAttrs.length > 0 && (
        <div className="space-y-1.5">
          {numericAttrs.slice(0, 6).map(([k, v]) => (
            <div key={k} className="flex items-center gap-2">
              <span className="text-[10px] text-slate-600 w-16 truncate capitalize">
                {k.slice(0, 3).toUpperCase()}
              </span>
              <div className="flex-1 stat-bar-track">
                <div
                  className="stat-bar-fill bg-purple-500"
                  style={{ width: `${(v / max) * 100}%` }}
                />
              </div>
              <span className="text-xs font-mono text-purple-300 w-8 text-right">{v}</span>
            </div>
          ))}
        </div>
      )}

      {char.state_tags.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {char.state_tags.slice(0, 3).map((t) => (
            <span key={t} className="tag-dim">{t}</span>
          ))}
          {char.state_tags.length > 3 && (
            <span className="tag-dim">+{char.state_tags.length - 3}</span>
          )}
        </div>
      )}
    </motion.div>
  );
}

// ─── Test roll panel ─────────────────────────────────────── 

function TestPanel({ systemId }: { systemId: string }) {
  const { data, isFetching, refetch, isError } = useQuery({
    queryKey: ["system-test", systemId],
    queryFn: () => entitiesApi.testSystem(systemId),
    enabled: false,
    retry: false,
  });

  const {
    data: npcData,
    isFetching: isNpcFetching,
    refetch: refetchNpc,
    isError: isNpcError,
  } = useQuery({
    queryKey: ["system-test-npc", systemId],
    queryFn: () => entitiesApi.testSystemNpc(systemId),
    enabled: false,
    retry: false,
  });

  return (
    <div className="space-y-4">
      <div className="glass rounded-2xl border border-white/5 p-5 space-y-3">
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <div className="flex items-center gap-2">
            <Dices className="w-4 h-4 text-purple-400" />
            <h3 className="text-xs font-semibold text-slate-300 uppercase tracking-wider">Test Character & NPC Generation</h3>
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            <button
              onClick={() => refetch()}
              disabled={isFetching}
              className={cn(
                "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all border",
                "border-purple-500/30 text-purple-300 hover:bg-purple-500/10 disabled:opacity-50"
              )}
            >
              {isFetching ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RotateCcw className="w-3.5 h-3.5" />}
              {isFetching ? "Rolling…" : data ? "Re-roll PC" : "Roll Character"}
            </button>
            <button
              onClick={() => refetchNpc()}
              disabled={isNpcFetching}
              className={cn(
                "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all border",
                "border-emerald-500/30 text-emerald-300 hover:bg-emerald-500/10 disabled:opacity-50"
              )}
            >
              {isNpcFetching ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RotateCcw className="w-3.5 h-3.5" />}
              {isNpcFetching ? "Generating…" : npcData ? "Re-roll NPC" : "Generate NPC"}
            </button>
          </div>
        </div>
        <p className="text-xs text-slate-600">
          Generates a random playable character or example NPC using this system&apos;s rules so you can verify attributes, formulas, and ranges.
        </p>
      </div>

      {(isError || isNpcError) && (
        <div className="glass-dark rounded-xl border border-red-500/20 px-4 py-3 text-xs text-red-400">
          Could not generate preview — ensure the agents service is running.
        </div>
      )}

      {data && (
        <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="space-y-4">
          <div className="glass rounded-2xl border border-white/5 p-5 space-y-3">
            <p className="text-[10px] font-bold tracking-widest uppercase text-slate-500">Character sheet — {data.system_name}</p>
            <pre className="text-xs text-slate-300 font-mono whitespace-pre-wrap leading-relaxed bg-black/20 rounded-xl p-4 overflow-x-auto">{data.sheet}</pre>
          </div>
          {data.attributes && Object.keys(data.attributes).length > 0 && (
            <div className="glass rounded-2xl border border-white/5 p-5 space-y-3">
              <p className="text-[10px] font-bold tracking-widest uppercase text-slate-500">Raw attributes</p>
              <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-2">
                {Object.entries(data.attributes as Record<string, number>).map(([k, v]) => (
                  <div key={k} className="glass-dark rounded-lg px-3 py-2 text-center">
                    <p className="text-xs font-mono font-bold text-cyan-300">{v}</p>
                    <p className="text-[10px] text-slate-600 mt-0.5 uppercase truncate">{k}</p>
                  </div>
                ))}
              </div>
            </div>
          )}
        </motion.div>
      )}

      {npcData && (
        <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="space-y-4">
          <div className="glass rounded-2xl border border-white/5 p-5 space-y-3">
            <p className="text-[10px] font-bold tracking-widest uppercase text-slate-500">NPC preview — {npcData.system_name}</p>
            <pre className="text-xs text-slate-300 font-mono whitespace-pre-wrap leading-relaxed bg-black/20 rounded-xl p-4 overflow-x-auto">{npcData.sheet}</pre>
          </div>
        </motion.div>
      )}
    </div>
  );
}

// ─── Characters panel ─────────────────────────────────────── 

function CharactersPanel({ systemId }: { systemId: string }) {
  const { data: characters = [], isLoading } = useQuery({
    queryKey: ENTITY_KEYS.characters(systemId),
    queryFn: () => entitiesApi.listCharacters(systemId),
  });

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 text-slate-500 text-sm p-4">
        <Loader2 className="w-4 h-4 animate-spin" /> Loading characters…
      </div>
    );
  }

  if (characters.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 space-y-2">
        <Users className="w-10 h-10 text-slate-700" />
        <p className="text-sm text-slate-600">No characters for this system yet.</p>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
      {characters.map((c) => (
        <CharacterCard key={c.id} char={c} />
      ))}
    </div>
  );
}

// ─── Main page ────────────────────────────────────────────── 

const SYSTEM_TABS = [
  { id: "overview", label: "Overview", icon: Layers },
  { id: "attributes", label: "Attributes", icon: Shield },
  { id: "rules", label: "Rules", icon: ListChecks },
  { id: "characters", label: "Characters", icon: Users },
  { id: "test", label: "Test Roll", icon: Dices },
] as const;

type TabId = typeof SYSTEM_TABS[number]["id"];

export default function SystemsPage() {
  const qc = useQueryClient();
  const [activeSystemId, setActiveSystemId] = useState<string | null>(null);
  const [tab, setTab] = useState<TabId>("overview");

  const { data: systems = [], isLoading } = useSystems();

  const deleteSystem = useMutation({
    mutationFn: entitiesApi.deleteSystem,
    onSuccess: (_data, deletedId) => {
      qc.invalidateQueries({ queryKey: ENTITY_KEYS.systems });
      if (activeSystemId === deletedId) setActiveSystemId(null);
    },
  });

  const activeSystem = systems.find((s) => s.id === activeSystemId);

  return (
    <div className="flex h-full">
      {/* Systems sidebar */}
      <div className="glass flex-shrink-0 w-64 flex flex-col border-r border-white/5 overflow-hidden">
        <div className="px-4 py-4 border-b border-white/5">
          <p className="section-label">Library</p>
          <h2 className="text-sm font-semibold text-slate-200 mt-1">RPG Systems</h2>
        </div>

        <div className="flex-1 overflow-y-auto">
          {isLoading && (
            <div className="flex items-center gap-2 text-slate-500 text-sm p-4">
              <Loader2 className="w-4 h-4 animate-spin" /> Loading…
            </div>
          )}
          {systems.length === 0 && !isLoading && (
            <div className="flex flex-col items-center py-12 px-4 space-y-2 text-center">
              <BookOpen className="w-8 h-8 text-slate-700" />
              <p className="text-xs text-slate-600">
                No RPG systems yet. Ingest a rulebook to discover systems.
              </p>
            </div>
          )}
          {systems.map((s) => (
            <SystemItem
              key={s.id}
              system={s}
              active={activeSystemId === s.id}
              onClick={() => { setActiveSystemId(s.id); setTab("overview"); }}
              onDelete={(id) => deleteSystem.mutate(id)}
            />
          ))}
        </div>
      </div>

      {/* Right panel */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {!activeSystem ? (
          <div className="flex-1 flex flex-col items-center justify-center space-y-4">
            <div className="w-16 h-16 rounded-2xl bg-purple-500/10 border border-purple-500/20 flex items-center justify-center">
              <Swords className="w-8 h-8 text-purple-400" />
            </div>
            <div className="text-center">
              <h2 className="text-lg font-semibold text-slate-200">RPG Systems</h2>
              <p className="text-sm text-slate-600 mt-1 max-w-xs">
                Select a system to view its rules, attributes, skills, and characters.
              </p>
            </div>
          </div>
        ) : (
          <>
            {/* Tabs */}
            <div className="flex items-center px-6 pt-5 pb-0 gap-1 border-b border-white/5">
              {SYSTEM_TABS.map(({ id, label, icon: Icon }) => (
                <button
                  key={id}
                  onClick={() => setTab(id)}
                  className={cn(
                    "flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition-all",
                    tab === id
                      ? "border-cyan-500 text-cyan-300"
                      : "border-transparent text-slate-500 hover:text-slate-300",
                  )}
                >
                  <Icon className="w-3.5 h-3.5" />
                  {label}
                  {id === "rules" && activeSystem.rules.length > 0 && (
                    <span className="text-[10px] bg-white/8 text-slate-500 rounded px-1">
                      {activeSystem.rules.length}
                    </span>
                  )}
                </button>
              ))}
            </div>

            {/* Content */}
            <div className="flex-1 overflow-y-auto px-6 py-5">
              <AnimatePresence mode="wait">
                <motion.div
                  key={`${activeSystemId}-${tab}`}
                  initial={{ opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0 }}
                  transition={{ duration: 0.2 }}
                >
                  {tab === "overview" && <SystemOverview system={activeSystem} />}
                  {tab === "attributes" && <AttributesPanel system={activeSystem} />}
                  {tab === "rules" && <RulesPanel system={activeSystem} />}
                  {tab === "characters" && <CharactersPanel systemId={activeSystem.id} />}
                  {tab === "test" && <TestPanel systemId={activeSystem.id} />}
                </motion.div>
              </AnimatePresence>
            </div>
          </>
        )}
      </div>
    </div>
  );
}


