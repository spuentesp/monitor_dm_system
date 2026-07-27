"use client";

/**
 * Apply Pack Wizard (MP-7 / MP-8)
 *
 * Entry: /forge/apply?pack=<pack_id>
 *
 * Steps:
 *  1. Target picker — New World | Existing World
 *  2a. New World   — confirm → POST /packs/{id}/apply/new-world          (MP-7)
 *  2b. Existing    — POST /packs/{id}/apply/{universe_id}
 *       If no conflicts  → success
 *       If conflicts     → Step 3: per-item resolution
 *       Step 4           → POST again with resolved_conflicts → commit  (MP-8)
 */

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  Bot,
  Check,
  CheckCircle2,
  ChevronDown,
  Globe2,
  Loader2,
  Package,
  Plus,
  Sparkles,
  XCircle,
} from "lucide-react";
import { ingestApi, universesApi } from "@/lib/api";
import type {
  KnowledgePack,
  Multiverse,
  PackApplySession,
  PackConflict,
  Universe,
} from "@/lib/types";
import { cn } from "@/lib/utils";

// ─── Step types ───────────────────────────────────────────────

type Target = "new" | "existing";
type Step = "target" | "new-confirm" | "existing-pick" | "conflicts" | "done";

// ─── Conflict resolution card ─────────────────────────────────

const RESOLUTIONS: Array<{
  value: PackConflict["resolution"];
  label: string;
  icon: React.ElementType;
  color: string;
}> = [
  { value: "pack_wins",    label: "Use pack value",  icon: Package,  color: "text-accent-primary" },
  { value: "world_wins",   label: "Keep world value", icon: Globe2,   color: "text-emerald-400"   },
  { value: "llm_merged",   label: "LLM suggestion",  icon: Sparkles, color: "text-purple-400"    },
  { value: "human_picked", label: "Custom value",    icon: Bot,      color: "text-amber-400"     },
];

function ConflictCard({
  conflict,
  index,
  resolution,
  customValue,
  onChange,
  onCustomChange,
}: {
  conflict: PackConflict;
  index: number;
  resolution: PackConflict["resolution"] | null;
  customValue: string;
  onChange: (r: PackConflict["resolution"]) => void;
  onCustomChange: (v: string) => void;
}) {
  const [showValues, setShowValues] = useState(false);

  return (
    <div className="border border-border rounded-lg bg-bg-card overflow-hidden">
      {/* Header */}
      <div className="flex items-center gap-3 px-4 py-2.5 border-b border-border bg-bg-hover">
        <span className="text-[10px] tag-red px-1.5 py-0.5 rounded border">{conflict.item_type}</span>
        <span className="text-sm font-semibold text-fg-primary">{conflict.item_name}</span>
        <button
          className="ml-auto text-[10px] text-fg-muted hover:text-fg-secondary flex items-center gap-1"
          onClick={() => setShowValues(v => !v)}
        >
          {showValues ? "Hide values" : "Show values"}
          <ChevronDown className={cn("h-3 w-3 transition-transform", showValues ? "rotate-180" : "")} />
        </button>
      </div>

      {/* Value diff */}
      <AnimatePresence initial={false}>
        {showValues && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="overflow-hidden"
          >
            <div className="grid grid-cols-2 gap-3 p-3 text-xs border-b border-border">
              <div>
                <p className="text-fg-muted mb-1">Pack value</p>
                <pre className="bg-bg-hover rounded p-2 text-fg-secondary text-[10px] overflow-auto max-h-24 whitespace-pre-wrap">
                  {typeof conflict.pack_value === "string"
                    ? conflict.pack_value
                    : JSON.stringify(conflict.pack_value, null, 2)}
                </pre>
              </div>
              <div>
                <p className="text-fg-muted mb-1">World value</p>
                <pre className="bg-bg-hover rounded p-2 text-fg-secondary text-[10px] overflow-auto max-h-24 whitespace-pre-wrap">
                  {typeof conflict.world_value === "string"
                    ? conflict.world_value
                    : JSON.stringify(conflict.world_value, null, 2)}
                </pre>
              </div>
            </div>
            {conflict.llm_suggestion && (
              <div className="px-3 py-2 border-b border-border text-xs">
                <p className="text-fg-muted mb-1 flex items-center gap-1">
                  <Sparkles className="h-3 w-3 text-purple-400" /> LLM suggestion
                </p>
                <pre className="bg-bg-hover rounded p-2 text-fg-secondary text-[10px] overflow-auto max-h-24 whitespace-pre-wrap">
                  {conflict.llm_suggestion}
                </pre>
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>

      {/* Resolution picker */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 p-3">
        {RESOLUTIONS.filter(r => r.value !== "llm_merged" || conflict.llm_suggestion).map(r => (
          <button
            key={r.value}
            onClick={() => onChange(r.value)}
            className={cn(
              "flex flex-col items-center gap-1 px-2 py-2 rounded-lg border text-xs font-medium transition-colors",
              resolution === r.value
                ? "border-accent-primary bg-accent-primary/10 text-accent-primary"
                : "border-border bg-bg-hover text-fg-muted hover:text-fg-secondary",
            )}
          >
            <r.icon className={cn("h-4 w-4", resolution === r.value ? "text-accent-primary" : r.color)} />
            {r.label}
          </button>
        ))}
      </div>

      {/* Custom value input */}
      <AnimatePresence initial={false}>
        {resolution === "human_picked" && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="overflow-hidden"
          >
            <div className="px-3 pb-3">
              <textarea
                className="input-base w-full text-xs resize-none"
                rows={3}
                placeholder="Enter your custom value (JSON or plain text)…"
                value={customValue}
                onChange={e => onCustomChange(e.target.value)}
              />
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

// ─── Step: target picker ──────────────────────────────────────

function TargetStep({
  target,
  onChange,
  onNext,
}: {
  target: Target | null;
  onChange: (t: Target) => void;
  onNext: () => void;
}) {
  return (
    <div className="space-y-4">
      <p className="text-xs text-fg-muted">Where do you want to apply this pack?</p>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {[
          { t: "new"      as Target, label: "New World",      desc: "Create a brand-new Multiverse + Universe from this pack.", icon: Plus   },
          { t: "existing" as Target, label: "Existing World", desc: "Apply to a universe you have already created.",            icon: Globe2 },
        ].map(({ t, label, desc, icon: Icon }) => (
          <button
            key={t}
            onClick={() => onChange(t)}
            className={cn(
              "text-left rounded-xl border p-4 transition-all",
              target === t
                ? "border-accent-primary bg-accent-primary/10"
                : "border-border hover:border-accent-primary/50 bg-bg-card",
            )}
          >
            <div className="flex items-center gap-2 mb-1">
              <Icon className={cn("h-4 w-4", target === t ? "text-accent-primary" : "text-fg-muted")} />
              <span className="text-sm font-semibold text-fg-primary">{label}</span>
              {target === t && <Check className="h-4 w-4 ml-auto text-accent-primary" />}
            </div>
            <p className="text-xs text-fg-muted">{desc}</p>
          </button>
        ))}
      </div>
      <div className="flex justify-end">
        <button className="btn-primary gap-1.5" disabled={!target} onClick={onNext}>
          <ArrowRight className="h-4 w-4" /> Next
        </button>
      </div>
    </div>
  );
}

// ─── Step: new world confirm ──────────────────────────────────

function NewWorldStep({
  packId,
  onDone,
}: {
  packId: string;
  onDone: (result: { world_name: string; universe_id: string }) => void;
}) {
  const [worldName, setWorldName]     = useState("");
  const [systemName, setSystemName]   = useState("");

  const applyMutation = useMutation({
    mutationFn: () =>
      ingestApi.applyPackNewWorld(packId, {
        world_name: worldName,
        system_name: systemName || undefined,
      }),
    onSuccess: (res) => {
      onDone({ world_name: worldName, universe_id: res.universe_id });
    },
  });

  return (
    <div className="space-y-4">
      <p className="text-xs text-fg-muted">
        A new Multiverse and Universe will be created from the pack's content.
      </p>
      <div className="space-y-3">
        <div>
          <label className="block text-xs text-fg-muted mb-1">World name *</label>
          <input
            autoFocus
            className="input-base w-full text-sm"
            placeholder="e.g. The Shattered Realm"
            value={worldName}
            onChange={e => setWorldName(e.target.value)}
          />
        </div>
        <div>
          <label className="block text-xs text-fg-muted mb-1">Game system (optional)</label>
          <input
            className="input-base w-full text-sm"
            placeholder="e.g. D&D 5e"
            value={systemName}
            onChange={e => setSystemName(e.target.value)}
          />
        </div>
      </div>
      {applyMutation.isError && (
        <div className="flex items-center gap-2 text-xs text-red-400">
          <AlertTriangle className="h-3.5 w-3.5" />
          {String(applyMutation.error)}
        </div>
      )}
      <div className="flex justify-end">
        <button
          className="btn-primary gap-1.5"
          disabled={!worldName.trim() || applyMutation.isPending}
          onClick={() => applyMutation.mutate()}
        >
          {applyMutation.isPending
            ? <Loader2 className="h-4 w-4 animate-spin" />
            : <><Globe2 className="h-4 w-4" /> Create World</>}
        </button>
      </div>
    </div>
  );
}

// ─── Step: existing world picker ──────────────────────────────

function ExistingWorldStep({
  packId,
  onReview,
  onNoConflicts,
}: {
  packId: string;
  onReview: (universeId: string, conflicts: PackConflict[]) => void;
  onNoConflicts: (universeId: string) => void;
}) {
  const [selectedMultiverse, setSelectedMultiverse] = useState<string>("");
  const [selectedUniverse, setSelectedUniverse]     = useState<string>("");
  const [autoCommitLlm, setAutoCommitLlm]           = useState(false);

  const { data: multiverses = [] } = useQuery({
    queryKey: ["multiverses"],
    queryFn: () => universesApi.listMultiverses(),
    staleTime: 30_000,
  });

  // Auto-select the first multiverse when data loads
  useEffect(() => {
    if (!selectedMultiverse && multiverses.length > 0) {
      setSelectedMultiverse(multiverses[0].id);
    }
  }, [multiverses, selectedMultiverse]);

  const { data: universes = [] } = useQuery({
    queryKey: ["universes", selectedMultiverse],
    queryFn: () => universesApi.listUniverses(selectedMultiverse || undefined),
    enabled: !!selectedMultiverse,
  });

  const applyMutation = useMutation({
    mutationFn: () =>
      ingestApi.applyPackExistingWorld(packId, selectedUniverse, {
        mode: "full",
        auto_commit_llm: autoCommitLlm,
      }),
    onSuccess: (res) => {
      const cfls = (res.conflicts ?? []) as PackConflict[];
      if (cfls.length > 0) {
        onReview(selectedUniverse, cfls);
      } else {
        onNoConflicts(selectedUniverse);
      }
    },
  });

  const filteredUniverses: Universe[] = universes.filter(
    u => !selectedMultiverse || u.multiverse_id === selectedMultiverse,
  );

  return (
    <div className="space-y-4">
      <p className="text-xs text-fg-muted">Choose the universe to apply this pack into.</p>

      {/* Multiverse picker — required, no "all" option */}
      <div>
        <label className="block text-xs text-fg-muted mb-1">Multiverse (setting) *</label>
        {multiverses.length === 0 ? (
          <p className="text-xs text-red-400">
            No multiverses found.{" "}
            <Link href="/forge/worlds" className="underline hover:text-red-300">
              Create one first in Forge → Worlds
            </Link>
            .
          </p>
        ) : (
          <select
            className="input-base w-full text-sm"
            value={selectedMultiverse}
            onChange={e => { setSelectedMultiverse(e.target.value); setSelectedUniverse(""); }}
          >
            {multiverses.map((m: Multiverse) => (
              <option key={m.id} value={m.id}>{m.name}</option>
            ))}
          </select>
        )}
      </div>

      {/* Universe list */}
      <div>
        <label className="block text-xs text-fg-muted mb-1">Target Universe *</label>
        <div className="border border-border rounded-lg overflow-hidden divide-y divide-border max-h-48 overflow-y-auto">
          {filteredUniverses.length === 0 && (
            <p className="text-xs text-fg-muted text-center py-6">No universes found.</p>
          )}
          {filteredUniverses.map(u => (
            <button
              key={u.id}
              onClick={() => setSelectedUniverse(u.id)}
              className={cn(
                "w-full text-left px-4 py-2.5 flex items-center gap-3 transition-colors",
                selectedUniverse === u.id
                  ? "bg-accent-primary/10 text-accent-primary"
                  : "hover:bg-bg-hover text-fg-primary",
              )}
            >
              <Globe2 className="h-4 w-4 shrink-0 text-fg-muted" />
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium">{u.name}</p>
                {u.genre && <p className="text-[10px] text-fg-muted">{u.genre}</p>}
              </div>
              <div className="text-xs text-fg-muted">{u.entity_count} entities</div>
              {selectedUniverse === u.id && <Check className="h-4 w-4 text-accent-primary shrink-0" />}
            </button>
          ))}
        </div>
      </div>

      {/* Auto-commit LLM toggle */}
      <label className="flex items-center gap-2 cursor-pointer">
        <div
          className={cn(
            "h-4 w-4 rounded border flex items-center justify-center shrink-0",
            autoCommitLlm ? "bg-accent-primary border-accent-primary" : "border-border",
          )}
          onClick={() => setAutoCommitLlm(v => !v)}
        >
          {autoCommitLlm && <Check className="h-3 w-3 text-white" />}
        </div>
        <input type="checkbox" className="sr-only" checked={autoCommitLlm} onChange={() => setAutoCommitLlm(v => !v)} />
        <div>
          <p className="text-xs text-fg-primary">Auto-commit LLM suggestions</p>
          <p className="text-[10px] text-fg-muted">LLM-resolved conflicts are committed without manual review</p>
        </div>
      </label>

      {applyMutation.isError && (
        <div className="flex items-center gap-2 text-xs text-red-400">
          <AlertTriangle className="h-3.5 w-3.5" />
          {String(applyMutation.error)}
        </div>
      )}

      <div className="flex justify-end">
        <button
          className="btn-primary gap-1.5"
          disabled={!selectedUniverse || applyMutation.isPending}
          onClick={() => applyMutation.mutate()}
        >
          {applyMutation.isPending
            ? <Loader2 className="h-4 w-4 animate-spin" />
            : <><ArrowRight className="h-4 w-4" /> Apply</>}
        </button>
      </div>
    </div>
  );
}

// ─── Step: conflict resolution ────────────────────────────────

function ConflictsStep({
  packId,
  universeId,
  conflicts,
  autoCommitLlm,
  onDone,
}: {
  packId: string;
  universeId: string;
  conflicts: PackConflict[];
  autoCommitLlm: boolean;
  onDone: () => void;
}) {
  type ResolutionMap = Record<number, { resolution: PackConflict["resolution"]; customValue: string }>;

  const [resolutions, setResolutions] = useState<ResolutionMap>(() => {
    const init: ResolutionMap = {};
    conflicts.forEach((c, i) => {
      if (c.llm_suggestion) {
        init[i] = { resolution: "llm_merged", customValue: "" };
      }
    });
    return init;
  });

  const allResolved = conflicts.every(
    (_, i) => resolutions[i]?.resolution != null,
  );

  const commitMutation = useMutation({
    mutationFn: () => {
      const resolved = conflicts.map((c, i) => {
        const r = resolutions[i];
        const base = {
          item_type: c.item_type,
          item_name: c.item_name,
          resolution: r?.resolution ?? "world_wins",
        };
        if (r?.resolution === "human_picked") {
          return { ...base, resolved_value: r.customValue };
        }
        return base;
      });
      return ingestApi.applyPackExistingWorld(packId, universeId, {
        mode: "full",
        auto_commit_llm: autoCommitLlm,
        resolved_conflicts: resolved,
      });
    },
    onSuccess: () => onDone(),
  });

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-amber-500/10 border border-amber-500/20 text-amber-400 text-xs">
        <AlertTriangle className="h-4 w-4 shrink-0" />
        <span><strong>{conflicts.length}</strong> conflict{conflicts.length !== 1 ? "s" : ""} found between the pack and the existing world. Resolve each one below.</span>
      </div>

      <div className="space-y-3">
        {conflicts.map((c, i) => (
          <ConflictCard
            key={i}
            conflict={c}
            index={i}
            resolution={resolutions[i]?.resolution ?? null}
            customValue={resolutions[i]?.customValue ?? ""}
            onChange={r => setResolutions(prev => ({ ...prev, [i]: { ...prev[i], resolution: r } }))}
            onCustomChange={v => setResolutions(prev => ({ ...prev, [i]: { ...prev[i], customValue: v } }))}
          />
        ))}
      </div>

      {commitMutation.isError && (
        <div className="flex items-center gap-2 text-xs text-red-400">
          <AlertTriangle className="h-3.5 w-3.5" />
          {String(commitMutation.error)}
        </div>
      )}

      <div className="flex justify-end">
        <button
          className="btn-primary gap-1.5"
          disabled={!allResolved || commitMutation.isPending}
          onClick={() => commitMutation.mutate()}
        >
          {commitMutation.isPending
            ? <Loader2 className="h-4 w-4 animate-spin" />
            : <><Check className="h-4 w-4" /> Commit {conflicts.length} changes</>}
        </button>
      </div>
    </div>
  );
}

// ─── Step labels ──────────────────────────────────────────────

const STEP_LABELS: Record<Step, string> = {
  "target":         "1. Choose target",
  "new-confirm":    "2. New world",
  "existing-pick":  "2. Pick universe",
  "conflicts":      "3. Resolve conflicts",
  "done":           "Done",
};

// ─── Apply page ───────────────────────────────────────────────

function ApplyPackPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const packId = searchParams.get("pack") ?? "";

  const [step, setStep]         = useState<Step>("target");
  const [target, setTarget]     = useState<Target | null>(null);
  const [universeId, setUniverseId]   = useState("");
  const [conflicts, setConflicts]     = useState<PackConflict[]>([]);
  const [autoCommitLlm, setAutoCommitLlm] = useState(false);
  const [doneInfo, setDoneInfo] = useState<{ message: string; universe_id?: string } | null>(null);

  const { data: pack } = useQuery({
    queryKey: ["pack", packId],
    queryFn: () => ingestApi.getPack(packId),
    enabled: !!packId,
    staleTime: 60_000,
  });

  const steps: Step[] = target === "new"
    ? ["target", "new-confirm", "done"]
    : ["target", "existing-pick", ...(conflicts.length > 0 ? ["conflicts" as Step] : []), "done"];

  const stepIndex = steps.indexOf(step);

  return (
    <div className="max-w-2xl mx-auto p-6 space-y-6">
      {/* Back + title */}
      <div className="flex items-center gap-3">
        <button className="btn-ghost p-1.5" onClick={() => router.back()}>
          <ArrowLeft className="h-4 w-4" />
        </button>
        <div>
          <h1 className="text-base font-bold text-fg-primary">Apply Pack</h1>
          {pack && <p className="text-xs text-fg-muted">{pack.name}</p>}
        </div>
      </div>

      {/* Step progress */}
      {step !== "done" && (
        <div className="flex items-center gap-1.5 text-xs text-fg-muted">
          {steps.filter(s => s !== "done").map((s, idx) => (
            <div key={s} className="flex items-center gap-1.5">
              {idx > 0 && <span className="text-fg-muted/40 select-none">/</span>}
              <span className={cn("font-medium", s === step ? "text-accent-primary" : "text-fg-muted")}>
                {STEP_LABELS[s]}
              </span>
            </div>
          ))}
        </div>
      )}

      {/* Card */}
      <div className="bg-bg-card border border-border rounded-xl p-5">
        <AnimatePresence mode="wait">
          {step === "target" && (
            <motion.div key="target" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }}>
              <TargetStep
                target={target}
                onChange={setTarget}
                onNext={() => {
                  if (target === "new") setStep("new-confirm");
                  else setStep("existing-pick");
                }}
              />
            </motion.div>
          )}

          {step === "new-confirm" && (
            <motion.div key="new-confirm" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }}>
              <NewWorldStep
                packId={packId}
                onDone={({ world_name, universe_id }) => {
                  setDoneInfo({
                    message: `"${world_name}" was created successfully.`,
                    universe_id,
                  });
                  setStep("done");
                }}
              />
            </motion.div>
          )}

          {step === "existing-pick" && (
            <motion.div key="existing-pick" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }}>
              <ExistingWorldStep
                packId={packId}
                onReview={(uid, cfls) => {
                  setUniverseId(uid);
                  setConflicts(cfls);
                  setStep("conflicts");
                }}
                onNoConflicts={uid => {
                  setUniverseId(uid);
                  setDoneInfo({ message: "Pack applied successfully — no conflicts." });
                  setStep("done");
                }}
              />
            </motion.div>
          )}

          {step === "conflicts" && (
            <motion.div key="conflicts" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }}>
              <ConflictsStep
                packId={packId}
                universeId={universeId}
                conflicts={conflicts}
                autoCommitLlm={autoCommitLlm}
                onDone={() => {
                  setDoneInfo({ message: "All conflicts resolved — pack applied." });
                  setStep("done");
                }}
              />
            </motion.div>
          )}

          {step === "done" && doneInfo && (
            <motion.div
              key="done"
              initial={{ opacity: 0, scale: 0.96 }}
              animate={{ opacity: 1, scale: 1 }}
              className="flex flex-col items-center gap-4 py-6"
            >
              <CheckCircle2 className="h-10 w-10 text-emerald-400" />
              <p className="text-sm text-fg-primary text-center">{doneInfo.message}</p>
              <div className="flex gap-3">
                <button className="btn-ghost" onClick={() => router.push("/forge/packs")}>
                  Back to Packs
                </button>
                <button
                  className="btn-cyber text-xs gap-1"
                  onClick={() => router.push(`/forge/review?pack=${packId}`)}
                >
                  <Sparkles className="h-3.5 w-3.5" /> Review Proposals
                </button>
                {doneInfo.universe_id && (
                  <button
                    className="btn-primary"
                    onClick={() => router.push(`/universes?universe=${doneInfo.universe_id}`)}
                  >
                    Open World
                  </button>
                )}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}

export default function ApplyPackPage() {
  return (
    <Suspense fallback={<div className="p-6 text-sm text-fg-secondary">Loading apply wizard…</div>}>
      <ApplyPackPageContent />
    </Suspense>
  );
}
