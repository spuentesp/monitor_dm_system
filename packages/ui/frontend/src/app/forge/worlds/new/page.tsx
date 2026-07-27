"use client";

/**
 * World-creation wizard (F1-3) — one front door for the five creation paths.
 *
 * Step 1: method picker (Blank / Quick seed / From pack / Fork / Demo).
 * Step 2: the method's form — shared components, never duplicates:
 *   - Blank      → CreateMultiverseForm + CreateUniverseForm (same as the
 *                  Worlds hierarchy tab)
 *   - Quick seed → QuickSeedForm (same as Ingest Studio's QuickStartPanel)
 *   - From pack  → pack picker, then router push into the /forge/apply wizard
 *   - Fork       → universe picker + name (replaces the snapshots window.prompt)
 *   - Demo       → forgeApi.demoWorld (curated Millhaven)
 * Step 3: confirm + land on /forge/worlds?universe=<id>.
 *
 * Deep links: ?method=fork&universe=<id> (used by the Snapshots fork button).
 */

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { AnimatePresence, motion } from "framer-motion";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  Check,
  CheckCircle2,
  Gamepad2,
  GitFork,
  Globe2,
  Layers,
  Loader2,
  Network,
  Package,
  Plus,
  Sparkles,
  Wand2,
} from "lucide-react";
import { forgeApi, ingestApi, universesApi } from "@/lib/api";
import type { Multiverse, Universe } from "@/lib/types";
import { cn } from "@/lib/utils";
import { useWorldContext } from "@/lib/world-context";
import { CreateMultiverseForm } from "@/components/forge/worlds/CreateMultiverseForm";
import { CreateUniverseForm } from "@/components/forge/worlds/CreateUniverseForm";
import { QuickSeedForm } from "@/components/forge/worlds/QuickSeedForm";

// ─── Method definitions ───────────────────────────────────────

const METHODS = [
  {
    id: "blank",
    label: "Blank",
    desc: "Create an empty setting and universe, then build it yourself.",
    icon: Plus,
  },
  {
    id: "quick",
    label: "Quick seed",
    desc: "Describe your world in a sentence — MONITOR forges a playable setting.",
    icon: Wand2,
  },
  {
    id: "pack",
    label: "From pack",
    desc: "Create a world from an ingested knowledge pack.",
    icon: Package,
  },
  {
    id: "fork",
    label: "Fork",
    desc: "Deep-clone an existing universe — entities, facts, relationships.",
    icon: GitFork,
  },
  {
    id: "demo",
    label: "Demo",
    desc: "The curated Millhaven mystery. Instant and LLM-free.",
    icon: Sparkles,
  },
] as const;

type Method = (typeof METHODS)[number]["id"];

const METHOD_LABEL: Record<Method, string> = {
  blank: "Blank world",
  quick: "Quick seed",
  pack: "From pack",
  fork: "Fork universe",
  demo: "Demo world",
};

interface DoneInfo {
  name: string;
  universeId?: string;
  sessionId?: string | null;
  note?: string;
}

// ─── Step 1: method picker ────────────────────────────────────

function MethodPicker({ onPick }: { onPick: (m: Method) => void }) {
  return (
    <div className="space-y-4">
      <p className="text-xs text-slate-500">How do you want to create your world?</p>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {METHODS.map(({ id, label, desc, icon: Icon }) => (
          <button
            key={id}
            onClick={() => onPick(id)}
            data-testid={`method-${id}`}
            className="text-left rounded-xl border border-white/10 bg-white/[0.02] p-4 transition-all hover:border-purple-500/40 hover:bg-purple-500/5"
          >
            <div className="flex items-center gap-2 mb-1">
              <Icon className="w-4 h-4 text-purple-300" />
              <span className="text-sm font-semibold text-slate-200">{label}</span>
            </div>
            <p className="text-xs text-slate-500">{desc}</p>
          </button>
        ))}
      </div>
    </div>
  );
}

// ─── Step 2: Blank ────────────────────────────────────────────

function BlankFlow({ onDone }: { onDone: (info: DoneInfo) => void }) {
  const { setWorld } = useWorldContext();
  const [stage, setStage] = useState<"pick-mv" | "new-mv" | "new-universe">("pick-mv");
  const [mv, setMv] = useState<Multiverse | null>(null);

  const { data: multiverses = [], isLoading } = useQuery({
    queryKey: ["multiverses"],
    queryFn: universesApi.listMultiverses,
  });

  // No settings yet → go straight to the multiverse form.
  useEffect(() => {
    if (!isLoading && multiverses.length === 0 && stage === "pick-mv") {
      setStage("new-mv");
    }
  }, [isLoading, multiverses.length, stage]);

  const handleUniverseCreated = (universe: Universe) => {
    setWorld({
      multiverseId: universe.multiverse_id,
      universeId: universe.id,
      universeLabel: universe.name,
    });
    onDone({ name: universe.name, universeId: universe.id });
  };

  if (stage === "new-mv") {
    return (
      <div className="space-y-3">
        <p className="text-xs text-slate-500">Step 2a — create the setting (multiverse).</p>
        <CreateMultiverseForm
          onClose={() => setStage((s) => (s === "new-universe" ? s : "pick-mv"))}
          onCreated={(created) => {
            setMv(created);
            setStage("new-universe");
          }}
        />
      </div>
    );
  }

  if (stage === "new-universe" && mv) {
    return (
      <div className="space-y-3">
        <p className="text-xs text-slate-500">
          Step 2b — create a universe inside <span className="text-slate-300">{mv.name}</span>.
        </p>
        <CreateUniverseForm
          multiverseId={mv.id}
          onClose={() => setStage("pick-mv")}
          onCreated={handleUniverseCreated}
        />
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <p className="text-xs text-slate-500">Step 2a — pick the setting your universe lives in.</p>
      <div className="border border-white/10 rounded-lg overflow-hidden divide-y divide-white/5">
        <button
          onClick={() => setStage("new-mv")}
          className="w-full text-left px-4 py-2.5 flex items-center gap-3 text-purple-300 hover:bg-purple-500/5 transition-colors"
        >
          <Plus className="w-4 h-4 shrink-0" />
          <span className="text-sm font-medium">New setting…</span>
        </button>
        {multiverses.map((m) => (
          <button
            key={m.id}
            onClick={() => {
              setMv(m);
              setStage("new-universe");
            }}
            className="w-full text-left px-4 py-2.5 flex items-center gap-3 text-slate-200 hover:bg-white/5 transition-colors"
          >
            <Layers className="w-4 h-4 shrink-0 text-slate-500" />
            <span className="text-sm font-medium">{m.name}</span>
          </button>
        ))}
        {isLoading && (
          <p className="px-4 py-3 text-xs text-slate-600 flex items-center gap-2">
            <Loader2 className="w-3 h-3 animate-spin" /> Loading settings…
          </p>
        )}
      </div>
    </div>
  );
}

// ─── Step 2: From pack ────────────────────────────────────────

function PackPickerStep() {
  const router = useRouter();
  const { data: packs = [], isLoading } = useQuery({
    queryKey: ["packs"],
    queryFn: () => ingestApi.listPacks(),
  });

  return (
    <div className="space-y-3">
      <p className="text-xs text-slate-500">
        Pick a knowledge pack — the Apply wizard opens to finish the job.
      </p>
      <div className="border border-white/10 rounded-lg overflow-hidden divide-y divide-white/5 max-h-72 overflow-y-auto">
        {isLoading && (
          <p className="px-4 py-3 text-xs text-slate-600 flex items-center gap-2">
            <Loader2 className="w-3 h-3 animate-spin" /> Loading packs…
          </p>
        )}
        {!isLoading && packs.length === 0 && (
          <p className="px-4 py-6 text-xs text-slate-600 text-center">
            No packs yet. Ingest a source document first.
          </p>
        )}
        {packs.map((p) => (
          <button
            key={p.id}
            onClick={() => router.push(`/forge/apply?pack=${encodeURIComponent(p.id)}`)}
            className="w-full text-left px-4 py-2.5 flex items-center gap-3 text-slate-200 hover:bg-white/5 transition-colors"
          >
            <Package className="w-4 h-4 shrink-0 text-teal-400" />
            <span className="text-sm font-medium flex-1 min-w-0 truncate">{p.name}</span>
            <span className="text-[10px] text-slate-600">{p.status}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

// ─── Step 2: Fork ─────────────────────────────────────────────

function ForkStep({
  initialUniverseId,
  onDone,
}: {
  initialUniverseId: string | null;
  onDone: (info: DoneInfo) => void;
}) {
  const qc = useQueryClient();
  const { setWorld } = useWorldContext();
  const [mvId, setMvId] = useState("");
  const [universeId, setUniverseId] = useState(initialUniverseId ?? "");
  const [name, setName] = useState("");

  const { data: multiverses = [] } = useQuery({
    queryKey: ["multiverses"],
    queryFn: universesApi.listMultiverses,
  });

  const { data: universes = [], isLoading } = useQuery({
    queryKey: ["universes", mvId],
    queryFn: () => universesApi.listUniverses(mvId || undefined),
  });

  const forkMut = useMutation({
    mutationFn: () => universesApi.forkUniverse(universeId, { name: name.trim() }),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ["universes"] });
      qc.invalidateQueries({ queryKey: ["multiverses"] });
      const source = universes.find((u) => u.id === universeId);
      setWorld({
        multiverseId: source?.multiverse_id ?? null,
        universeId: res.new_universe_id,
        universeLabel: res.name,
      });
      onDone({
        name: res.name,
        universeId: res.new_universe_id,
        note: `${res.entities_cloned} entities and ${res.relationships_cloned} relationships cloned.`,
      });
    },
  });

  return (
    <div className="space-y-4">
      <p className="text-xs text-slate-500">
        Fork deep-clones all canon into an independent universe you can diverge safely.
      </p>

      <div>
        <label className="block text-xs text-slate-500 mb-1">Setting (optional filter)</label>
        <select
          className="input-cyber w-full text-sm py-1.5"
          value={mvId}
          onChange={(e) => {
            setMvId(e.target.value);
            setUniverseId("");
          }}
        >
          <option value="">All settings</option>
          {multiverses.map((m) => (
            <option key={m.id} value={m.id}>{m.name}</option>
          ))}
        </select>
      </div>

      <div>
        <label className="block text-xs text-slate-500 mb-1">Source universe *</label>
        <div className="border border-white/10 rounded-lg overflow-hidden divide-y divide-white/5 max-h-48 overflow-y-auto">
          {isLoading && (
            <p className="px-4 py-3 text-xs text-slate-600 flex items-center gap-2">
              <Loader2 className="w-3 h-3 animate-spin" /> Loading universes…
            </p>
          )}
          {!isLoading && universes.length === 0 && (
            <p className="px-4 py-6 text-xs text-slate-600 text-center">No universes found.</p>
          )}
          {universes.map((u) => (
            <button
              key={u.id}
              onClick={() => setUniverseId(u.id)}
              className={cn(
                "w-full text-left px-4 py-2.5 flex items-center gap-3 transition-colors",
                universeId === u.id
                  ? "bg-purple-500/10 text-purple-300"
                  : "text-slate-200 hover:bg-white/5",
              )}
            >
              <Globe2 className="w-4 h-4 shrink-0 text-slate-500" />
              <span className="text-sm font-medium flex-1 min-w-0 truncate">{u.name}</span>
              {universeId === u.id && <Check className="w-4 h-4 text-purple-300 shrink-0" />}
            </button>
          ))}
        </div>
      </div>

      <div>
        <label className="block text-xs text-slate-500 mb-1">Fork name *</label>
        <input
          className="input-cyber w-full text-sm"
          placeholder="e.g. Ashen Vale — what-if branch"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
      </div>

      {forkMut.isError && (
        <p className="text-xs text-red-300">
          {forkMut.error instanceof Error ? forkMut.error.message : "Fork failed."}
        </p>
      )}

      <div className="flex justify-end">
        <button
          className="btn-cyber text-sm"
          disabled={!universeId || !name.trim() || forkMut.isPending}
          onClick={() => forkMut.mutate()}
        >
          {forkMut.isPending ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <GitFork className="w-4 h-4" />
          )}
          Fork universe
        </button>
      </div>
    </div>
  );
}

// ─── Step 2: Demo ─────────────────────────────────────────────

function DemoStep({ onDone }: { onDone: (info: DoneInfo) => void }) {
  const { setWorld } = useWorldContext();

  const demoMut = useMutation({
    mutationFn: () => forgeApi.demoWorld(true),
    onSuccess: (res) => {
      setWorld({
        multiverseId: res.multiverse_id,
        universeId: res.universe_id,
        universeLabel: res.world_name,
      });
      onDone({
        name: res.world_name,
        universeId: res.universe_id,
        sessionId: res.session_id,
        note: res.reused ? "The existing Millhaven demo world was reused." : undefined,
      });
    },
  });

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-amber-500/20 bg-amber-500/5 p-4 space-y-2">
        <p className="text-sm font-semibold text-slate-200 flex items-center gap-2">
          <Sparkles className="w-4 h-4 text-amber-400" /> Millhaven
        </p>
        <p className="text-xs text-slate-400 leading-relaxed">
          A fog-bound village where people disappear after dark. Five curated entities, a
          world-truth, a pregen character, and a ready-to-play session — deterministic, no LLM
          required.
        </p>
      </div>

      {demoMut.isError && (
        <p className="text-xs text-red-300">
          {demoMut.error instanceof Error ? demoMut.error.message : "Could not create the demo world."}
        </p>
      )}

      <div className="flex justify-end">
        <button
          className="btn-cyber text-sm"
          disabled={demoMut.isPending}
          onClick={() => demoMut.mutate()}
        >
          {demoMut.isPending ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <Sparkles className="w-4 h-4" />
          )}
          {demoMut.isPending ? "Creating…" : "Create demo world"}
        </button>
      </div>
    </div>
  );
}

// ─── Step 3: confirm ──────────────────────────────────────────

function ConfirmStep({ info, onReset }: { info: DoneInfo; onReset: () => void }) {
  return (
    <div className="flex flex-col items-center gap-4 py-6 text-center">
      <CheckCircle2 className="w-10 h-10 text-emerald-400" />
      <div>
        <p className="text-sm text-slate-200">
          <span className="font-semibold">"{info.name}"</span> is ready.
        </p>
        {info.note && <p className="text-xs text-slate-500 mt-1">{info.note}</p>}
      </div>
      <div className="flex flex-wrap justify-center gap-2">
        {info.sessionId && (
          <Link href={`/play?session=${info.sessionId}`} className="btn-cyber text-xs py-2">
            <Gamepad2 className="w-3.5 h-3.5" /> Play now
          </Link>
        )}
        {info.universeId && (
          <Link
            href={`/forge/worlds?universe=${encodeURIComponent(info.universeId)}`}
            className="btn-cyber text-xs py-2"
            data-testid="confirm-open-world"
          >
            <Network className="w-3.5 h-3.5" /> Open in Worlds
          </Link>
        )}
        <button onClick={onReset} className="btn-ghost text-xs py-2 border border-white/10">
          <Plus className="w-3.5 h-3.5" /> Create another
        </button>
      </div>
    </div>
  );
}

// ─── Wizard page ──────────────────────────────────────────────

function NewWorldWizard() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const paramMethod = searchParams.get("method");
  const initialMethod: Method | null = METHODS.some((m) => m.id === paramMethod)
    ? (paramMethod as Method)
    : null;
  const initialUniverseId = searchParams.get("universe");

  const [method, setMethod] = useState<Method | null>(initialMethod);
  const [done, setDone] = useState<DoneInfo | null>(null);

  const handleDone = (info: DoneInfo) => setDone(info);
  const reset = () => {
    setDone(null);
    setMethod(null);
  };

  const stepLabel = done
    ? "3. Done"
    : method
      ? `2. ${METHOD_LABEL[method]}`
      : "1. Choose method";

  return (
    <div className="max-w-2xl mx-auto p-6 space-y-6">
      {/* Back + title */}
      <div className="flex items-center gap-3">
        <button
          className="btn-ghost p-1.5"
          aria-label="Back to Worlds"
          onClick={() => router.push("/forge/worlds")}
        >
          <ArrowLeft className="w-4 h-4" />
        </button>
        <div>
          <h1 className="text-base font-bold text-slate-100">New World</h1>
          <p className="text-xs text-slate-500">Five ways in — pick one.</p>
        </div>
      </div>

      {/* Step progress */}
      <div className="flex items-center gap-1.5 text-xs text-slate-500">
        <span className={cn("font-medium", !method && !done && "text-purple-300")}>
          1. Choose method
        </span>
        <span className="text-slate-700 select-none">/</span>
        <span className={cn("font-medium", method && !done ? "text-purple-300" : "text-slate-600")}>
          {method ? `2. ${METHOD_LABEL[method]}` : "2. Create"}
        </span>
        <span className="text-slate-700 select-none">/</span>
        <span className={cn("font-medium", done ? "text-purple-300" : "text-slate-600")}>
          3. Done
        </span>
        <span className="sr-only">{stepLabel}</span>
      </div>

      {/* Card */}
      <div className="glass rounded-2xl border border-white/10 p-5">
        <AnimatePresence mode="wait">
          {done ? (
            <motion.div
              key="done"
              initial={{ opacity: 0, scale: 0.96 }}
              animate={{ opacity: 1, scale: 1 }}
            >
              <ConfirmStep info={done} onReset={reset} />
            </motion.div>
          ) : method === null ? (
            <motion.div
              key="picker"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
            >
              <MethodPicker onPick={setMethod} />
            </motion.div>
          ) : (
            <motion.div
              key={method}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              className="space-y-4"
            >
              <button
                onClick={() => setMethod(null)}
                className="text-xs text-slate-500 hover:text-slate-300 flex items-center gap-1"
              >
                <ArrowLeft className="w-3 h-3" /> All methods
              </button>
              {method === "blank" && <BlankFlow onDone={handleDone} />}
              {method === "quick" && <QuickSeedForm showHeader={false} />}
              {method === "pack" && <PackPickerStep />}
              {method === "fork" && (
                <ForkStep initialUniverseId={initialUniverseId} onDone={handleDone} />
              )}
              {method === "demo" && <DemoStep onDone={handleDone} />}
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}

export default function NewWorldPage() {
  return (
    <Suspense fallback={<div className="p-6 text-sm text-slate-500">Loading wizard…</div>}>
      <NewWorldWizard />
    </Suspense>
  );
}
