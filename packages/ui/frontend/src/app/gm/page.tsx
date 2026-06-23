"use client";

import { Suspense, useState, useEffect } from "react";
import { useSearchParams } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { useQuery, useMutation } from "@tanstack/react-query";
import {
  BookOpen,
  ChevronDown,
  ClipboardList,
  Dices,
  GitBranch,
  Globe2,
  Layers,
  Loader2,
  Mic,
  NotebookPen,
  RefreshCw,
  Save,
  Sparkles,
  Upload,
  X,
  Check,
  AlertTriangle,
  Scroll,
} from "lucide-react";
import { entitiesApi, ingestApi, universesApi, gmApi, storiesApi } from "@/lib/api";
import type { PlotHook, Contradiction, SessionPrep, Handout, StoryThread } from "@/lib/types";
import { cn } from "@/lib/utils";
import { SessionRecorder } from "@/components/gm/SessionRecorder";
import { useWorldContext } from "@/lib/world-context";

// ═══════════════════════════════════════════════════════════════
//  Dice roller
// ═══════════════════════════════════════════════════════════════

interface RollResult {
  id: string;
  expression: string;
  rolls: number[];
  modifier: number;
  total: number;
  timestamp: string;
}

function rollDie(sides: number): number {
  return Math.floor(Math.random() * sides) + 1;
}

function parseDiceExpression(expr: string): { rolls: number[]; modifier: number; total: number } | null {
  const clean = expr.trim().toLowerCase().replace(/\s/g, "");
  const match = clean.match(/^(\d+)?d(\d+)([+-]\d+)?$/);
  if (!match) return null;
  const count = parseInt(match[1] ?? "1", 10);
  const sides = parseInt(match[2], 10);
  const mod = parseInt(match[3] ?? "0", 10);
  if (count < 1 || count > 100 || sides < 2 || sides > 1000) return null;
  const rolls = Array.from({ length: count }, () => rollDie(sides));
  const total = rolls.reduce((a, b) => a + b, 0) + mod;
  return { rolls, modifier: mod, total };
}

const QUICK_DICE: Array<{ label: string; sides: number; color: string; border: string; bg: string }> = [
  { label: "d4",   sides: 4,   color: "text-pink-300",   border: "border-pink-500/30",   bg: "bg-pink-500/8"   },
  { label: "d6",   sides: 6,   color: "text-amber-300",  border: "border-amber-500/30",  bg: "bg-amber-500/8"  },
  { label: "d8",   sides: 8,   color: "text-orange-300", border: "border-orange-500/30", bg: "bg-orange-500/8" },
  { label: "d10",  sides: 10,  color: "text-emerald-300",border: "border-emerald-500/30",bg: "bg-emerald-500/8"},
  { label: "d12",  sides: 12,  color: "text-cyan-300",   border: "border-cyan-500/30",   bg: "bg-cyan-500/8"   },
  { label: "d20",  sides: 20,  color: "text-purple-300", border: "border-purple-500/30", bg: "bg-purple-500/8" },
  { label: "d100", sides: 100, color: "text-slate-300",  border: "border-slate-500/30",  bg: "bg-slate-500/8"  },
];

function DiceRoller() {
  const [history, setHistory] = useState<RollResult[]>([]);
  const [expr, setExpr] = useState("1d20");
  const [diceCount, setDiceCount] = useState(1);

  const doRoll = (expression: string) => {
    const result = parseDiceExpression(expression);
    if (!result) return;
    const entry: RollResult = {
      id: crypto.randomUUID(),
      expression,
      ...result,
      timestamp: new Date().toLocaleTimeString(),
    };
    setHistory((h) => [entry, ...h].slice(0, 20));
  };

  return (
    <div className="flex flex-col h-full space-y-4 overflow-hidden">
      {/* Quick dice */}
      <div className="grid grid-cols-4 gap-2">
        {QUICK_DICE.map((d) => (
          <button
            key={d.sides}
            onClick={() => doRoll(`${diceCount}d${d.sides}`)}
            className={cn("flex flex-col items-center gap-1 py-3 rounded-xl border transition-all hover:scale-105 active:scale-95", d.border, d.bg)}
          >
            <Dices className={cn("w-4 h-4", d.color)} />
            <span className={cn("text-xs font-bold", d.color)}>{d.label}</span>
          </button>
        ))}
      </div>

      {/* Dice count */}
      <div className="flex items-center gap-3">
        <label className="text-xs text-slate-500 w-20">Dice count</label>
        <input
          type="number"
          min={1}
          max={20}
          value={diceCount}
          onChange={(e) => setDiceCount(Math.max(1, Math.min(20, parseInt(e.target.value, 10) || 1)))}
          className="w-14 rounded border border-white/10 bg-white/4 px-2 py-1.5 text-center text-sm font-bold text-slate-200 focus:border-cyan-500/50 focus:outline-none"
        />
      </div>

      {/* Expression input */}
      <div className="flex gap-2">
        <input
          value={expr}
          onChange={(e) => setExpr(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") doRoll(expr); }}
          placeholder="e.g. 2d6+3"
          className="input-cyber flex-1 text-sm font-mono"
        />
        <button onClick={() => doRoll(expr)} className="btn-cyber px-3">
          <Dices className="w-4 h-4" />
        </button>
      </div>

      {/* Roll history */}
      <div className="flex-1 overflow-y-auto space-y-2 min-h-0">
        <AnimatePresence initial={false}>
          {history.map((roll) => {
            const isCrit = roll.rolls.length > 0 && Math.max(...roll.rolls) >= parseInt(roll.expression.split("d")[1] ?? "0", 10);
            const isFumble = roll.rolls.length > 0 && Math.max(...roll.rolls) === 1 && roll.rolls.every((r) => r === 1);
            return (
              <motion.div
                key={roll.id}
                initial={{ opacity: 0, x: 12 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -12 }}
                className={cn(
                  "glass-dark rounded-xl border px-3 py-2.5",
                  isCrit ? "border-amber-500/30 bg-amber-500/5" : isFumble ? "border-red-500/30 bg-red-500/5" : "border-white/5",
                )}
              >
                <div className="flex items-center justify-between">
                  <span className="text-xs font-mono text-slate-400">{roll.expression}</span>
                  <span className={cn("text-sm font-bold", isCrit ? "text-amber-300" : isFumble ? "text-red-400" : "text-slate-100")}>
                    {roll.total}
                  </span>
                </div>
                <div className="flex items-center justify-between mt-0.5">
                  <span className="text-[10px] text-slate-600">
                    [{roll.rolls.join(", ")}]{roll.modifier !== 0 ? ` ${roll.modifier > 0 ? "+" : ""}${roll.modifier}` : ""}
                  </span>
                  <span className="text-[10px] text-slate-700">{roll.timestamp}</span>
                </div>
              </motion.div>
            );
          })}
        </AnimatePresence>
        {history.length === 0 && (
          <div className="text-center py-8">
            <Dices className="w-8 h-8 text-slate-700 mx-auto mb-2" />
            <p className="text-xs text-slate-600">No rolls yet</p>
          </div>
        )}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
//  Rules reference
// ═══════════════════════════════════════════════════════════════

function RulesPanel({ systemId }: { systemId: string | null }) {
  const { data: system, isLoading } = useQuery({
    queryKey: ["system-detail", systemId],
    queryFn: () => entitiesApi.getSystem(systemId!),
    enabled: Boolean(systemId),
  });

  if (!systemId) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-center space-y-2 px-4">
        <BookOpen className="w-8 h-8 text-slate-700" />
        <p className="text-xs text-slate-600">Select an RPG system to see rules reference</p>
      </div>
    );
  }
  if (isLoading) return <div className="flex items-center justify-center h-full"><Loader2 className="w-5 h-5 text-slate-600 animate-spin" /></div>;
  if (!system) return <div className="p-4 text-xs text-slate-600">System not found.</div>;

  return (
    <div className="overflow-y-auto h-full px-4 py-4 space-y-5">
      {/* Core mechanic */}
      {system.core_mechanic && (
        <section className="space-y-2">
          <h3 className="text-[10px] font-bold tracking-widest uppercase text-emerald-400">Core Mechanic</h3>
          <div className="glass-dark rounded-xl border border-white/5 p-3 space-y-1.5">
            {system.core_mechanic.formula && <p className="text-xs font-mono text-slate-300">{system.core_mechanic.formula}</p>}
            {system.core_mechanic.description && <p className="text-xs text-slate-500 leading-relaxed">{system.core_mechanic.description}</p>}
            <div className="flex gap-3 text-[10px] text-slate-600">
              {system.core_mechanic.success_type && <span>Success: {system.core_mechanic.success_type}</span>}
              {system.core_mechanic.target_number != null && <span>Target: {system.core_mechanic.target_number}</span>}
            </div>
          </div>
        </section>
      )}

      {/* Attributes */}
      {system.attributes.length > 0 && (
        <section className="space-y-2">
          <h3 className="text-[10px] font-bold tracking-widest uppercase text-cyan-400">Attributes</h3>
          <div className="grid grid-cols-2 gap-1.5">
            {system.attributes.map((a) => (
              <div key={a.name} className="glass-dark rounded-lg border border-white/5 px-2.5 py-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold text-slate-200">{a.abbreviation ?? a.name}</span>
                  {a.min_value != null && a.max_value != null && (
                    <span className="text-[10px] text-slate-600">{a.min_value}–{a.max_value}</span>
                  )}
                </div>
                {a.description && <p className="text-[10px] text-slate-600 mt-0.5 leading-relaxed truncate">{a.description}</p>}
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Resources */}
      {system.resources.length > 0 && (
        <section className="space-y-2">
          <h3 className="text-[10px] font-bold tracking-widest uppercase text-purple-400">Resources</h3>
          <div className="space-y-1">
            {system.resources.map((r) => (
              <div key={r.name} className="glass-dark rounded-lg border border-white/5 px-2.5 py-2 flex items-center justify-between">
                <span className="text-xs font-medium text-slate-200">{r.name}</span>
                <div className="text-[10px] text-slate-600 space-x-2">
                  {r.max_value != null && <span>Max {r.max_value}</span>}
                  {r.recovers_on && <span>Recovers: {r.recovers_on}</span>}
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Rules */}
      {system.rules.length > 0 && (
        <section className="space-y-2">
          <h3 className="text-[10px] font-bold tracking-widest uppercase text-amber-400">Rules</h3>
          <div className="space-y-2">
            {system.rules.map((r) => {
              const [open, setOpen] = useState(false);
              return (
                <div key={r.name} className="group glass-dark rounded-xl border border-white/5 overflow-hidden">
                  <button
                    onClick={() => setOpen((o) => !o)}
                    className="w-full px-3 py-2.5 cursor-pointer flex items-center justify-between"
                  >
                    <span className="text-xs font-medium text-slate-200">{r.name}</span>
                    <div className="flex items-center gap-2">
                      <span className="text-[10px] text-slate-600 bg-white/5 px-1.5 py-0.5 rounded">{r.rule_type}</span>
                      <ChevronDown className={cn("w-3.5 h-3.5 text-slate-600 transition-transform duration-200", open && "rotate-[-180deg]")} />
                    </div>
                  </button>
                  <AnimatePresence initial={false}>
                    {open && (
                      <motion.div
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: "auto", opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        transition={{ duration: 0.2 }}
                        className="overflow-hidden"
                      >
                        <div className="px-3 pb-3 space-y-1.5">
                          {r.description && <p className="text-xs text-slate-400 leading-relaxed">{r.description}</p>}
                          {r.formula && <code className="block text-xs font-mono text-emerald-300 bg-emerald-500/5 rounded px-2 py-1">{r.formula}</code>}
                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </div>
              );
            })}
          </div>
        </section>
      )}

      {system.description && (
        <section className="space-y-2">
          <h3 className="text-[10px] font-bold tracking-widest uppercase text-slate-600">About</h3>
          <p className="text-xs text-slate-500 leading-relaxed">{system.description}</p>
        </section>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
//  Session notebook
// ═══════════════════════════════════════════════════════════════

function SessionNotebook({
  universeId,
  multiverseId,
}: {
  universeId: string | null;
  multiverseId?: string | null;
}) {
  const [notes, setNotes] = useState("");
  const [saved, setSaved] = useState(false);
  const [ingestStatus, setIngestStatus] = useState<"idle" | "pending" | "done" | "error">("idle");
  const STORAGE_KEY = `gm-notebook-${universeId ?? "default"}`;

  // Load from localStorage when universe changes
  useState(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved) setNotes(saved);
    } catch {
      // ignore
    }
  });

  const saveNotes = () => {
    try {
      localStorage.setItem(STORAGE_KEY, notes);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch {
      // ignore
    }
  };

  const ingestNotes = useMutation({
    mutationFn: async () => {
      const blob = new Blob([notes], { type: "text/plain" });
      const file = new File([blob], "session-notes.txt", { type: "text/plain" });
      return ingestApi.uploadSource(file, {
        scan_type: "full",
        analysis_layers: ["axioms", "entities", "lore"],
        multiverse_id: multiverseId ?? undefined,
        title: `Session notes — ${new Date().toLocaleDateString()}`,
      });
    },
    onSuccess: () => setIngestStatus("done"),
    onError: () => setIngestStatus("error"),
    onMutate: () => setIngestStatus("pending"),
  });

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Toolbar */}
      <div className="flex items-center gap-2 px-4 py-2 border-b border-white/5 flex-shrink-0">
        <span className="text-[10px] font-bold tracking-widest uppercase text-slate-600 flex-1">Session Notes</span>
        <AnimatePresence>
          {saved && (
            <motion.span initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="text-xs text-emerald-400 flex items-center gap-1">
              <Check className="w-3 h-3" /> Saved
            </motion.span>
          )}
        </AnimatePresence>
        <button onClick={saveNotes} className="btn-ghost text-xs py-0.5 px-2"><Save className="w-3 h-3" /> Save</button>
        <button
          onClick={() => ingestNotes.mutate()}
          disabled={!notes.trim() || ingestNotes.isPending}
          className={cn("btn-ghost text-xs py-0.5 px-2", !notes.trim() && "opacity-40 cursor-not-allowed")}
          title="Ingest notes into the world knowledge base"
        >
          {ingestNotes.isPending ? <Loader2 className="w-3 h-3 animate-spin" /> : <Upload className="w-3 h-3" />} Ingest
        </button>
      </div>

      {/* Textarea */}
      <textarea
        value={notes}
        onChange={(e) => setNotes(e.target.value)}
        placeholder={[
          "# Session Notes",
          "",
          "Record events, NPC dialogue, player decisions, and clues here.",
          "When you're done, click Ingest to update the world knowledge base.",
          "",
          "Example:",
          "- The party descended into the ancient vault beneath Ironwatch.",
          "- Mira discovered a hidden passage behind the waterfall.",
          "- BBEG Malachar revealed he was working with the Merchants' Guild.",
        ].join("\n")}
        className="flex-1 bg-transparent text-sm text-slate-300 font-mono leading-relaxed resize-none p-4 focus:outline-none placeholder:text-slate-700"
        spellCheck={false}
      />

      {/* Status bar */}
      <div className="flex items-center justify-between px-4 py-2 border-t border-white/5 flex-shrink-0">
        <span className="text-[10px] text-slate-700">
          {notes.length} chars · {notes.split("\n").length} lines
        </span>
        {ingestStatus === "done" && (
          <span className="text-[10px] text-emerald-400 flex items-center gap-1"><Check className="w-3 h-3" /> Queued for ingestion</span>
        )}
        {ingestStatus === "error" && (
          <span className="text-[10px] text-red-400">Ingestion failed — check ingest jobs</span>
        )}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
//  Plot Hooks Panel (CF-4)
// ═══════════════════════════════════════════════════════════════

function PlotHooksPanel({ universeId }: { universeId: string | null }) {
  const [hooks, setHooks] = useState<PlotHook[]>([]);

  const mutation = useMutation({
    mutationFn: () => gmApi.suggestHooks(universeId!),
    onSuccess: (data) => setHooks(data.hooks),
  });

  if (!universeId) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-center space-y-2 px-4">
        <Sparkles className="w-8 h-8 text-slate-700" />
        <p className="text-xs text-slate-600">Select a universe to generate plot hooks</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <div className="flex items-center gap-2 px-4 py-3 border-b border-white/5 flex-shrink-0">
        <Sparkles className="w-3.5 h-3.5 text-amber-400" />
        <span className="text-xs font-semibold text-slate-300 flex-1">Plot Hooks</span>
        <button
          onClick={() => mutation.mutate()}
          disabled={mutation.isPending}
          className="btn-cyber text-xs py-1 px-3"
        >
          {mutation.isPending ? <Loader2 className="w-3 h-3 animate-spin" /> : <RefreshCw className="w-3 h-3" />}
          Generate
        </button>
      </div>
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
        {mutation.isPending && hooks.length === 0 && (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="w-5 h-5 text-slate-600 animate-spin" />
          </div>
        )}
        {mutation.isError && (
          <div className="text-xs text-red-400 text-center py-4">Failed to generate hooks. Try again.</div>
        )}
        {hooks.map((hook, i) => (
          <div key={i} className="glass-dark rounded-xl border border-white/5 p-3 space-y-1.5">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-slate-200">{hook.title}</span>
              <span className={cn(
                "text-[10px] px-1.5 py-0.5 rounded font-medium",
                hook.urgency === "critical" ? "bg-red-500/15 text-red-400" :
                hook.urgency === "high" ? "bg-amber-500/15 text-amber-400" :
                hook.urgency === "medium" ? "bg-cyan-500/15 text-cyan-400" :
                "bg-slate-500/15 text-slate-400"
              )}>
                {hook.urgency}
              </span>
            </div>
            <p className="text-xs text-slate-400 leading-relaxed">{hook.description}</p>
            {hook.connected_entities.length > 0 && (
              <div className="flex flex-wrap gap-1 mt-1">
                {hook.connected_entities.map((e, j) => (
                  <span key={j} className="text-[10px] bg-white/5 px-1.5 py-0.5 rounded text-slate-500">{e}</span>
                ))}
              </div>
            )}
            <div className="text-[10px] text-slate-600">
              Suggested scene: <span className="text-slate-400">{hook.suggested_scene_type}</span>
            </div>
          </div>
        ))}
        {!mutation.isPending && hooks.length === 0 && (
          <div className="text-center py-8">
            <Sparkles className="w-8 h-8 text-slate-700 mx-auto mb-2" />
            <p className="text-xs text-slate-600">Click Generate to discover plot hooks</p>
          </div>
        )}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
//  Contradiction Detection Panel (CF-5)
// ═══════════════════════════════════════════════════════════════

function ContradictionsPanel({ universeId }: { universeId: string | null }) {
  const [contradictions, setContradictions] = useState<Contradiction[]>([]);

  const mutation = useMutation({
    mutationFn: () => gmApi.detectContradictions(universeId!),
    onSuccess: (data) => setContradictions(data.contradictions),
  });

  if (!universeId) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-center space-y-2 px-4">
        <AlertTriangle className="w-8 h-8 text-slate-700" />
        <p className="text-xs text-slate-600">Select a universe to detect contradictions</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <div className="flex items-center gap-2 px-4 py-3 border-b border-white/5 flex-shrink-0">
        <AlertTriangle className="w-3.5 h-3.5 text-amber-400" />
        <span className="text-xs font-semibold text-slate-300 flex-1">Contradictions</span>
        <button
          onClick={() => mutation.mutate()}
          disabled={mutation.isPending}
          className="btn-cyber text-xs py-1 px-3"
        >
          {mutation.isPending ? <Loader2 className="w-3 h-3 animate-spin" /> : <RefreshCw className="w-3 h-3" />}
          Detect
        </button>
      </div>
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
        {mutation.isPending && contradictions.length === 0 && (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="w-5 h-5 text-slate-600 animate-spin" />
          </div>
        )}
        {mutation.isError && (
          <div className="text-xs text-red-400 text-center py-4">Failed to detect contradictions. Try again.</div>
        )}
        {contradictions.map((c, i) => (
          <div key={i} className="glass-dark rounded-xl border border-white/5 p-3 space-y-2">
            <div className="flex items-center justify-between">
              <span className={cn(
                "text-[10px] px-1.5 py-0.5 rounded font-medium",
                c.severity === "high" ? "bg-red-500/15 text-red-400" :
                c.severity === "medium" ? "bg-amber-500/15 text-amber-400" :
                "bg-slate-500/15 text-slate-400"
              )}>
                {c.severity} severity
              </span>
            </div>
            <div className="space-y-1">
              <div className="text-xs text-slate-300 bg-red-500/5 rounded px-2 py-1 border-l-2 border-red-500/30">
                {c.fact_a}
              </div>
              <div className="text-xs text-slate-300 bg-red-500/5 rounded px-2 py-1 border-l-2 border-red-500/30">
                {c.fact_b}
              </div>
            </div>
            <p className="text-xs text-slate-500">{c.explanation}</p>
            <p className="text-xs text-cyan-400/80">💡 {c.suggestion}</p>
          </div>
        ))}
        {!mutation.isPending && contradictions.length === 0 && (
          <div className="text-center py-8">
            <AlertTriangle className="w-8 h-8 text-slate-700 mx-auto mb-2" />
            <p className="text-xs text-slate-600">Click Detect to find contradictions</p>
          </div>
        )}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
//  Session Prep Panel (CF-7)
// ═══════════════════════════════════════════════════════════════

function SessionPrepPanel({ universeId }: { universeId: string | null }) {
  const [prep, setPrep] = useState<SessionPrep | null>(null);
  const [storyId, setStoryId] = useState("");

  const { data: storiesData } = useQuery({
    queryKey: ["universe-stories", universeId],
    queryFn: () => storiesApi.listStories({ universe_id: universeId!, limit: 100 }),
    enabled: !!universeId,
    staleTime: 15_000,
  });
  const stories = storiesData?.stories ?? [];

  // Default to the most recent story once loaded
  useEffect(() => {
    if (!storyId && stories.length > 0) setStoryId(stories[0].id);
    if (storyId && stories.length > 0 && !stories.some((s) => s.id === storyId)) {
      setStoryId(stories[0].id);
    }
  }, [stories, storyId]);

  const mutation = useMutation({
    mutationFn: () => gmApi.generateSessionPrep(universeId!, storyId),
    onSuccess: (data) => setPrep(data.prep),
  });

  if (!universeId) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-center space-y-2 px-4">
        <ClipboardList className="w-8 h-8 text-slate-700" />
        <p className="text-xs text-slate-600">Select a universe to generate session prep</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <div className="flex items-center gap-2 px-4 py-3 border-b border-white/5 flex-shrink-0">
        <ClipboardList className="w-3.5 h-3.5 text-emerald-400" />
        <span className="text-xs font-semibold text-slate-300 flex-1">Session Prep</span>
        <select
          value={storyId}
          onChange={(e) => setStoryId(e.target.value)}
          className="input-cyber py-1 text-xs max-w-[170px]"
          disabled={stories.length === 0}
          title="Which story to prep for"
        >
          {stories.length === 0 && <option value="">No stories yet</option>}
          {stories.map((s) => (
            <option key={s.id} value={s.id}>
              {s.title} ({s.status})
            </option>
          ))}
        </select>
        <button
          onClick={() => mutation.mutate()}
          disabled={mutation.isPending || !storyId}
          className={cn("btn-cyber text-xs py-1 px-3", !storyId && "opacity-40 cursor-not-allowed")}
        >
          {mutation.isPending ? <Loader2 className="w-3 h-3 animate-spin" /> : <Sparkles className="w-3 h-3" />}
          Generate
        </button>
      </div>
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-4">
        {mutation.isPending && !prep && (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="w-5 h-5 text-slate-600 animate-spin" />
          </div>
        )}
        {mutation.isError && (
          <div className="text-xs text-red-400 text-center py-4">Failed to generate session prep. Try again.</div>
        )}
        {prep && (
          <>
            {/* Recap */}
            <section className="space-y-1.5">
              <h3 className="text-[10px] font-bold tracking-widest uppercase text-emerald-400">Recap</h3>
              <p className="text-xs text-slate-300 leading-relaxed glass-dark rounded-xl border border-white/5 p-3">
                {prep.recap}
              </p>
            </section>

            {/* Open Threads */}
            {prep.open_threads.length > 0 && (
              <section className="space-y-1.5">
                <h3 className="text-[10px] font-bold tracking-widest uppercase text-amber-400">Open Threads</h3>
                <ul className="space-y-1">
                  {prep.open_threads.map((t, i) => (
                    <li key={i} className="text-xs text-slate-400 flex items-start gap-1.5">
                      <span className="text-amber-500 mt-0.5">•</span> {t}
                    </li>
                  ))}
                </ul>
              </section>
            )}

            {/* Hooks */}
            {prep.hooks.length > 0 && (
              <section className="space-y-1.5">
                <h3 className="text-[10px] font-bold tracking-widest uppercase text-cyan-400">Suggested Hooks</h3>
                {prep.hooks.map((h, i) => (
                  <div key={i} className="glass-dark rounded-lg border border-white/5 p-2.5">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-medium text-slate-200">{h.title}</span>
                      <span className="text-[10px] text-slate-600">{h.urgency}</span>
                    </div>
                    <p className="text-[11px] text-slate-500 mt-0.5">{h.description}</p>
                  </div>
                ))}
              </section>
            )}

            {/* NPC Reminders */}
            {prep.npc_reminders.length > 0 && (
              <section className="space-y-1.5">
                <h3 className="text-[10px] font-bold tracking-widest uppercase text-purple-400">NPC Reminders</h3>
                <div className="flex flex-wrap gap-1.5">
                  {prep.npc_reminders.map((npc, i) => (
                    <span key={i} className="text-xs bg-purple-500/10 text-purple-300 px-2 py-1 rounded-lg border border-purple-500/20">
                      {npc}
                    </span>
                  ))}
                </div>
              </section>
            )}

            {/* World State Changes */}
            {prep.world_state_changes.length > 0 && (
              <section className="space-y-1.5">
                <h3 className="text-[10px] font-bold tracking-widest uppercase text-slate-400">World Changes</h3>
                <ul className="space-y-1">
                  {prep.world_state_changes.map((c, i) => (
                    <li key={i} className="text-xs text-slate-500 flex items-start gap-1.5">
                      <span className="text-slate-600 mt-0.5">•</span> {c}
                    </li>
                  ))}
                </ul>
              </section>
            )}
          </>
        )}
        {!mutation.isPending && !prep && (
          <div className="text-center py-8">
            <ClipboardList className="w-8 h-8 text-slate-700 mx-auto mb-2" />
            <p className="text-xs text-slate-600">Pick a story and click Generate</p>
          </div>
        )}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
//  Unresolved Threads Panel (CF-3)
// ═══════════════════════════════════════════════════════════════

const THREAD_URGENCY_TAG: Record<string, string> = {
  immediate: "bg-red-500/15 text-red-400",
  high: "bg-amber-500/15 text-amber-400",
  medium: "bg-cyan-500/15 text-cyan-400",
  low: "bg-slate-500/15 text-slate-400",
};

function ThreadsPanel({ universeId }: { universeId: string | null }) {
  const [storyId, setStoryId] = useState("");

  const { data: storiesData } = useQuery({
    queryKey: ["universe-stories", universeId],
    queryFn: () => storiesApi.listStories({ universe_id: universeId!, limit: 100 }),
    enabled: !!universeId,
    staleTime: 15_000,
  });
  const stories = storiesData?.stories ?? [];

  useEffect(() => {
    if (!storyId && stories.length > 0) setStoryId(stories[0].id);
    if (storyId && stories.length > 0 && !stories.some((s) => s.id === storyId)) {
      setStoryId(stories[0].id);
    }
  }, [stories, storyId]);

  const { data: threads = [], isLoading } = useQuery({
    queryKey: ["story-threads", storyId],
    queryFn: () => storiesApi.listThreads(storyId),
    enabled: !!storyId,
    staleTime: 30_000,
    retry: 1,
  });

  if (!universeId) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-center space-y-2 px-4">
        <GitBranch className="w-8 h-8 text-slate-700" />
        <p className="text-xs text-slate-600">Select a universe to track unresolved threads</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <div className="flex items-center gap-2 px-4 py-3 border-b border-white/5 flex-shrink-0">
        <GitBranch className="w-3.5 h-3.5 text-purple-400" />
        <span className="text-xs font-semibold text-slate-300 flex-1">Unresolved Threads</span>
        <select
          value={storyId}
          onChange={(e) => setStoryId(e.target.value)}
          className="input-cyber py-1 text-xs max-w-[170px]"
          disabled={stories.length === 0}
        >
          {stories.length === 0 && <option value="">No stories yet</option>}
          {stories.map((s) => (
            <option key={s.id} value={s.id}>
              {s.title} ({s.status})
            </option>
          ))}
        </select>
      </div>
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-2">
        {isLoading && (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="w-5 h-5 text-slate-600 animate-spin" />
          </div>
        )}
        {!isLoading && threads.length === 0 && (
          <div className="text-center py-8">
            <GitBranch className="w-8 h-8 text-slate-700 mx-auto mb-2" />
            <p className="text-xs text-slate-600">
              {storyId ? "No open threads in this story" : "Pick a story to see its loose ends"}
            </p>
          </div>
        )}
        {threads.map((t: StoryThread, i) => (
          <div key={t.id ?? `${t.title}-${i}`} className="glass-dark rounded-xl border border-white/5 p-3 space-y-1.5">
            <div className="flex items-center justify-between gap-2">
              <span className="text-xs font-medium text-slate-200 leading-snug">{t.title}</span>
              {t.urgency && (
                <span className={cn("text-[10px] px-1.5 py-0.5 rounded font-medium flex-shrink-0", THREAD_URGENCY_TAG[t.urgency] ?? THREAD_URGENCY_TAG.low)}>
                  {t.urgency}
                </span>
              )}
            </div>
            <div className="flex items-center gap-2 text-[10px] text-slate-600">
              {t.thread_type && <span className="capitalize">{t.thread_type.replace(/_/g, " ")}</span>}
              <span className="capitalize">{t.status.replace(/_/g, " ")}</span>
              {t.source === "checkpoint" && <span className="italic">from story state</span>}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
//  Player Handouts Panel (CF-6)
// ═══════════════════════════════════════════════════════════════

const HANDOUT_TYPES = [
  { value: "letter", label: "Letter", icon: "✉️" },
  { value: "map_note", label: "Map Note", icon: "🗺️" },
  { value: "prophecy", label: "Prophecy", icon: "🔮" },
  { value: "journal_entry", label: "Journal", icon: "📓" },
  { value: "notice", label: "Notice", icon: "📜" },
  { value: "rumor", label: "Rumor", icon: "🗣️" },
] as const;

const HANDOUT_TONES = ["mysterious", "urgent", "warm", "ominous", "neutral"] as const;
const SPOILER_LEVELS = ["safe", "partial", "full"] as const;

function HandoutsPanel({ universeId }: { universeId: string | null }) {
  const [handout, setHandout] = useState<Handout | null>(null);
  const [handoutType, setHandoutType] = useState<string>("letter");
  const [tone, setTone] = useState<string>("mysterious");
  const [spoilerLevel, setSpoilerLevel] = useState<string>("safe");

  const mutation = useMutation({
    mutationFn: () =>
      gmApi.generateHandout(universeId!, {
        handout_type: handoutType,
        tone,
        spoiler_level: spoilerLevel,
      }),
    onSuccess: (data) => setHandout(data.handout),
  });

  if (!universeId) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-center space-y-2 px-4">
        <Scroll className="w-8 h-8 text-slate-700" />
        <p className="text-xs text-slate-600">Select a universe to generate handouts</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <div className="flex items-center gap-2 px-4 py-3 border-b border-white/5 flex-shrink-0">
        <Scroll className="w-3.5 h-3.5 text-amber-400" />
        <span className="text-xs font-semibold text-slate-300 flex-1">Handouts</span>
        <button
          onClick={() => mutation.mutate()}
          disabled={mutation.isPending}
          className="btn-cyber text-xs py-1 px-3"
        >
          {mutation.isPending ? <Loader2 className="w-3 h-3 animate-spin" /> : <Sparkles className="w-3 h-3" />}
          Generate
        </button>
      </div>

      {/* Controls */}
      <div className="px-4 py-2 space-y-2 border-b border-white/5 flex-shrink-0">
        {/* Handout type */}
        <div className="flex flex-wrap gap-1.5">
          {HANDOUT_TYPES.map((t) => (
            <button
              key={t.value}
              onClick={() => setHandoutType(t.value)}
              className={cn(
                "text-[10px] px-2 py-1 rounded-lg border transition-all",
                handoutType === t.value
                  ? "bg-amber-500/15 text-amber-300 border-amber-500/30"
                  : "text-slate-500 border-white/5 hover:text-slate-300 hover:bg-white/4"
              )}
            >
              {t.icon} {t.label}
            </button>
          ))}
        </div>
        {/* Tone & spoiler */}
        <div className="flex gap-3">
          <div className="flex items-center gap-1.5">
            <span className="text-[10px] text-slate-600">Tone:</span>
            <select
              value={tone}
              onChange={(e) => setTone(e.target.value)}
              className="input-cyber py-0.5 text-[10px] w-24"
            >
              {HANDOUT_TONES.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="text-[10px] text-slate-600">Spoilers:</span>
            <select
              value={spoilerLevel}
              onChange={(e) => setSpoilerLevel(e.target.value)}
              className="input-cyber py-0.5 text-[10px] w-20"
            >
              {SPOILER_LEVELS.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
        </div>
      </div>

      {/* Handout content */}
      <div className="flex-1 overflow-y-auto px-4 py-3">
        {mutation.isPending && !handout && (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="w-5 h-5 text-slate-600 animate-spin" />
          </div>
        )}
        {mutation.isError && (
          <div className="text-xs text-red-400 text-center py-4">Failed to generate handout. Try again.</div>
        )}
        {handout && (
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold text-slate-200">{handout.title}</h3>
              <div className="flex items-center gap-1.5">
                <span className="text-[10px] bg-white/5 px-1.5 py-0.5 rounded text-slate-500">{handout.handout_type}</span>
                <span className={cn(
                  "text-[10px] px-1.5 py-0.5 rounded",
                  handout.spoiler_level === "full" ? "bg-red-500/15 text-red-400" :
                  handout.spoiler_level === "partial" ? "bg-amber-500/15 text-amber-400" :
                  "bg-emerald-500/15 text-emerald-400"
                )}>
                  {handout.spoiler_level}
                </span>
              </div>
            </div>
            <div className="glass-dark rounded-xl border border-white/5 p-4">
              <div className="prose prose-sm prose-invert max-w-none text-xs text-slate-300 leading-relaxed whitespace-pre-wrap">
                {handout.content}
              </div>
            </div>
            {handout.related_entities.length > 0 && (
              <div className="flex flex-wrap gap-1.5">
                {handout.related_entities.map((e, i) => (
                  <span key={i} className="text-[10px] bg-cyan-500/10 text-cyan-400 px-2 py-0.5 rounded-lg border border-cyan-500/20">
                    {e}
                  </span>
                ))}
              </div>
            )}
          </div>
        )}
        {!mutation.isPending && !handout && (
          <div className="text-center py-8">
            <Scroll className="w-8 h-8 text-slate-700 mx-auto mb-2" />
            <p className="text-xs text-slate-600">Choose a handout type and click Generate</p>
          </div>
        )}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
//  Universe + System selector
// ═══════════════════════════════════════════════════════════════

function GMSelector({
  universeId,
  systemId,
  onUniverseChange,
  onSystemChange,
  onMultiverseChange,
}: {
  universeId: string | null;
  systemId: string | null;
  onUniverseChange: (id: string | null, label?: string | null) => void;
  onSystemChange: (id: string | null) => void;
  onMultiverseChange?: (id: string | null) => void;
}) {
  const { data: multiverses = [] } = useQuery({ queryKey: ["multiverses"], queryFn: universesApi.listMultiverses });
  const [selectedMv, setSelectedMv] = useState<string | null>(null);

  const { data: universes = [] } = useQuery({
    queryKey: ["universes", selectedMv],
    queryFn: () => universesApi.listUniverses(selectedMv ?? undefined),
    enabled: true,
  });

  const { data: systems = [] } = useQuery({
    queryKey: ["systems"],
    queryFn: entitiesApi.listSystems,
  });

  // Keep the multiverse callback in sync (the notebook binds ingestion to it)
  useEffect(() => {
    const owner = universes.find((u) => u.id === universeId)?.multiverse_id ?? selectedMv;
    onMultiverseChange?.(owner ?? null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedMv, universeId, universes.length]);

  return (
    <div className="flex items-center gap-3 flex-wrap">
      <div className="flex items-center gap-1.5">
        <Layers className="w-3.5 h-3.5 text-purple-400 flex-shrink-0" />
        <select value={selectedMv ?? ""} onChange={(e) => { setSelectedMv(e.target.value || null); onUniverseChange(null); }} className="input-cyber py-1 text-xs min-w-[120px]">
          <option value="">All multiverses</option>
          {multiverses.map((mv) => <option key={mv.id} value={mv.id}>{mv.name}</option>)}
        </select>
      </div>
      <div className="flex items-center gap-1.5">
        <Globe2 className="w-3.5 h-3.5 text-cyan-400 flex-shrink-0" />
        <select
          value={universeId ?? ""}
          onChange={(e) => {
            const id = e.target.value || null;
            onUniverseChange(id, universes.find((u) => u.id === id)?.name ?? null);
          }}
          className="input-cyber py-1 text-xs min-w-[140px]"
        >
          <option value="">Select universe…</option>
          {universes.map((uv) => <option key={uv.id} value={uv.id}>{uv.name}</option>)}
        </select>
      </div>
      {systems.length > 0 && (
        <div className="flex items-center gap-1.5">
          <BookOpen className="w-3.5 h-3.5 text-emerald-400 flex-shrink-0" />
          <select value={systemId ?? ""} onChange={(e) => onSystemChange(e.target.value || null)} className="input-cyber py-1 text-xs min-w-[140px]">
            <option value="">No system selected</option>
            {systems.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
//  Page
// ═══════════════════════════════════════════════════════════════

const GM_PANELS = [
  { id: "rules",          label: "Rules",          icon: BookOpen },
  { id: "recorder",       label: "Recorder",       icon: Mic },
  { id: "notebook",       label: "Scratchpad",     icon: NotebookPen },
  { id: "dice",           label: "Dice",            icon: Dices },
  { id: "hooks",          label: "Hooks",          icon: Sparkles },
  { id: "threads",        label: "Threads",        icon: GitBranch },
  { id: "contradictions", label: "Contradictions",  icon: AlertTriangle },
  { id: "session-prep",   label: "Prep",            icon: ClipboardList },
  { id: "handouts",       label: "Handouts",        icon: Scroll },
] as const;

type GMPanel = (typeof GM_PANELS)[number]["id"];

const TOOL_PANEL_IDS: GMPanel[] = ["hooks", "threads", "contradictions", "session-prep", "handouts"];

function GMAssistantPageContent() {
  const searchParams = useSearchParams();
  const requestedUniverseId = searchParams.get("universe");
  const [universeId, setUniverseId] = useState<string | null>(requestedUniverseId);
  const [universeLabel, setUniverseLabel] = useState<string | null>(null);
  const [multiverseId, setMultiverseId] = useState<string | null>(null);
  const [systemId, setSystemId] = useState<string | null>(null);
  const [activePanel, setActivePanel] = useState<GMPanel>("recorder");
  const [centerTab, setCenterTab] = useState<"recorder" | "notebook">("recorder");

  // Resolve a deep-linked universe's label once
  const { data: requestedUniverse } = useQuery({
    queryKey: ["universe", requestedUniverseId],
    queryFn: () => universesApi.getUniverse(requestedUniverseId!),
    enabled: !!requestedUniverseId,
  });
  useEffect(() => {
    if (requestedUniverse && universeId === requestedUniverse.id && !universeLabel) {
      setUniverseLabel(requestedUniverse.name);
    }
  }, [requestedUniverse, universeId, universeLabel]);

  // No URL param → adopt the persisted global world once it hydrates (T-077)
  const world = useWorldContext();
  useEffect(() => {
    if (!requestedUniverseId && !universeId && world.universeId) {
      setUniverseId(world.universeId);
      setUniverseLabel(world.universeLabel);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [world.universeId]);

  const handleUniverseChange = (id: string | null, label?: string | null) => {
    setUniverseId(id);
    setUniverseLabel(label ?? null);
  };

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Header */}
      <div className="flex items-center gap-4 px-6 py-3 border-b border-white/5 glass-dark flex-shrink-0 flex-wrap">
        <ClipboardList className="w-5 h-5 text-emerald-400 flex-shrink-0" />
        <h1 className="text-sm font-bold text-slate-200">GM Assistant</h1>
        <div className="h-5 w-px bg-white/10" />
        <GMSelector
          universeId={universeId}
          systemId={systemId}
          onUniverseChange={handleUniverseChange}
          onSystemChange={setSystemId}
          onMultiverseChange={setMultiverseId}
        />

        {/* Panel tabs (mobile/narrow only; desktop has fixed columns) */}
        <div className="ml-auto flex items-center gap-1 xl:hidden">
          {GM_PANELS.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              onClick={() => setActivePanel(id)}
              className={cn(
                "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all border",
                activePanel === id
                  ? "bg-emerald-500/10 text-emerald-300 border-emerald-500/25"
                  : "text-slate-500 hover:text-slate-300 border-transparent hover:bg-white/4",
              )}
            >
              <Icon className="w-3.5 h-3.5" />
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* Three-panel layout (desktop: side by side, controlled via tab on mobile) */}
      <div className="flex-1 overflow-hidden">
        <div className="hidden xl:flex h-full">
          {/* Rules */}
          <div className="w-72 flex-shrink-0 border-r border-white/5 flex flex-col overflow-hidden">
            <div className="px-4 py-3 border-b border-white/5 flex-shrink-0">
              <div className="flex items-center gap-2">
                <BookOpen className="w-3.5 h-3.5 text-emerald-400" />
                <span className="text-xs font-semibold text-slate-300">Rules Reference</span>
              </div>
            </div>
            <div className="flex-1 overflow-hidden">
              <RulesPanel systemId={systemId} />
            </div>
          </div>

          {/* Center: Recorder / Scratchpad */}
          <div className="flex-1 border-r border-white/5 flex flex-col overflow-hidden">
            <div className="flex items-center gap-1 px-3 py-2 border-b border-white/5 flex-shrink-0">
              {([
                { id: "recorder", label: "Session Recorder", icon: Mic },
                { id: "notebook", label: "Scratchpad", icon: NotebookPen },
              ] as const).map(({ id, label, icon: Icon }) => (
                <button
                  key={id}
                  onClick={() => setCenterTab(id)}
                  className={cn(
                    "flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-medium transition-all border",
                    centerTab === id
                      ? "bg-emerald-500/10 text-emerald-300 border-emerald-500/25"
                      : "text-slate-500 hover:text-slate-300 border-transparent hover:bg-white/4",
                  )}
                >
                  <Icon className="w-3 h-3" />
                  {label}
                </button>
              ))}
            </div>
            <div className="flex-1 overflow-hidden flex flex-col">
              {centerTab === "recorder" ? (
                universeId ? (
                  <SessionRecorder universeId={universeId} universeLabel={universeLabel} />
                ) : (
                  <div className="flex-1 flex flex-col items-center justify-center text-center space-y-2 px-4">
                    <Mic className="w-8 h-8 text-slate-700" />
                    <p className="text-xs text-slate-600">Select a universe to record a session into it</p>
                  </div>
                )
              ) : (
                <SessionNotebook universeId={universeId} multiverseId={multiverseId} />
              )}
            </div>
          </div>

          {/* GM Tools column */}
          <div className="w-96 flex-shrink-0 flex flex-col overflow-hidden">
            {/* Sub-tabs for GM tools */}
            <div className="flex items-center gap-1 px-3 py-2 border-b border-white/5 flex-shrink-0 overflow-x-auto">
              {GM_PANELS.filter((p) => TOOL_PANEL_IDS.includes(p.id)).map(({ id, label, icon: Icon }) => (
                <button
                  key={id}
                  onClick={() => setActivePanel(id as GMPanel)}
                  className={cn(
                    "flex items-center gap-1 px-2 py-1 rounded-lg text-[10px] font-medium transition-all border whitespace-nowrap",
                    activePanel === id
                      ? "bg-emerald-500/10 text-emerald-300 border-emerald-500/25"
                      : "text-slate-500 hover:text-slate-300 border-transparent hover:bg-white/4"
                  )}
                >
                  <Icon className="w-3 h-3" />
                  {label}
                </button>
              ))}
            </div>
            <div className="flex-1 overflow-hidden">
              {activePanel === "hooks" && <PlotHooksPanel universeId={universeId} />}
              {activePanel === "threads" && <ThreadsPanel universeId={universeId} />}
              {activePanel === "contradictions" && <ContradictionsPanel universeId={universeId} />}
              {activePanel === "session-prep" && <SessionPrepPanel universeId={universeId} />}
              {activePanel === "handouts" && <HandoutsPanel universeId={universeId} />}
              {/* Default to hooks if a non-tool panel is active */}
              {!TOOL_PANEL_IDS.includes(activePanel) && <PlotHooksPanel universeId={universeId} />}
            </div>
          </div>

          {/* Dice */}
          <div className="w-64 flex-shrink-0 flex flex-col overflow-hidden px-4 py-4">
            <div className="flex items-center gap-2 mb-4">
              <Dices className="w-3.5 h-3.5 text-emerald-400" />
              <span className="text-xs font-semibold text-slate-300">Dice Roller</span>
            </div>
            <DiceRoller />
          </div>
        </div>

        {/* Mobile / narrow: single panel view */}
        <div className="xl:hidden h-full flex flex-col overflow-hidden">
          <AnimatePresence mode="wait">
            <motion.div
              key={activePanel}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -6 }}
              transition={{ duration: 0.12 }}
              className="flex-1 overflow-hidden flex flex-col"
            >
              {activePanel === "rules" && (
                <div className="flex-1 overflow-hidden">
                  <RulesPanel systemId={systemId} />
                </div>
              )}
              {activePanel === "recorder" && (
                <div className="flex-1 overflow-hidden flex flex-col">
                  {universeId ? (
                    <SessionRecorder universeId={universeId} universeLabel={universeLabel} />
                  ) : (
                    <div className="flex-1 flex flex-col items-center justify-center text-center space-y-2 px-4">
                      <Mic className="w-8 h-8 text-slate-700" />
                      <p className="text-xs text-slate-600">Select a universe to record a session into it</p>
                    </div>
                  )}
                </div>
              )}
              {activePanel === "notebook" && (
                <div className="flex-1 overflow-hidden flex flex-col">
                  <SessionNotebook universeId={universeId} multiverseId={multiverseId} />
                </div>
              )}
              {activePanel === "dice" && (
                <div className="flex-1 overflow-hidden px-4 py-4">
                  <DiceRoller />
                </div>
              )}
              {activePanel === "hooks" && (
                <div className="flex-1 overflow-hidden">
                  <PlotHooksPanel universeId={universeId} />
                </div>
              )}
              {activePanel === "threads" && (
                <div className="flex-1 overflow-hidden">
                  <ThreadsPanel universeId={universeId} />
                </div>
              )}
              {activePanel === "contradictions" && (
                <div className="flex-1 overflow-hidden">
                  <ContradictionsPanel universeId={universeId} />
                </div>
              )}
              {activePanel === "session-prep" && (
                <div className="flex-1 overflow-hidden">
                  <SessionPrepPanel universeId={universeId} />
                </div>
              )}
              {activePanel === "handouts" && (
                <div className="flex-1 overflow-hidden">
                  <HandoutsPanel universeId={universeId} />
                </div>
              )}
            </motion.div>
          </AnimatePresence>
        </div>
      </div>
    </div>
  );
}

export default function GMAssistantPage() {
  return (
    <Suspense fallback={<div className="p-6 text-sm text-slate-500">Loading GM assistant…</div>}>
      <GMAssistantPageContent />
    </Suspense>
  );
}
