"use client";

import { useState } from "react";
import Link from "next/link";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { motion, AnimatePresence } from "framer-motion";
import {
  AlertCircle,
  Gamepad2,
  Globe2,
  Loader2,
  MapPin,
  Network,
  Shield,
  Sparkles,
  User,
  Wand2,
} from "lucide-react";
import { forgeApi, type QuickWorldResult } from "@/lib/api";
import { useWorldContext } from "@/lib/world-context";
import { cn } from "@/lib/utils";

const GENRES = [
  "dark fantasy",
  "high fantasy",
  "cyberpunk",
  "sci-fi",
  "cosmic horror",
  "noir",
  "post-apocalyptic",
  "urban fantasy",
  "steampunk",
  "western",
];

const TONES = ["grim", "heroic", "mysterious", "dramatic", "adventure", "horror"];

const SEED_EXAMPLES = [
  "A rain-soaked harbor city where the drowned barter for the memories they lost at sea.",
  "A frontier mining moon where the ore whispers and the company owns your air.",
  "A monastery on the last mountain above an endless white fog that eats names.",
];

const ENTITY_ICON: Record<string, React.ElementType> = {
  character: User,
  location: MapPin,
  faction: Shield,
  object: Sparkles,
  concept: Sparkles,
  organization: Shield,
};

function ResultCard({ result }: { result: QuickWorldResult }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="glass rounded-2xl border border-emerald-500/20 p-5 space-y-4"
    >
      <div className="flex items-start gap-3">
        <div className="w-10 h-10 rounded-xl bg-emerald-500/10 border border-emerald-500/25 flex items-center justify-center flex-shrink-0">
          <Globe2 className="w-5 h-5 text-emerald-400" />
        </div>
        <div className="min-w-0 flex-1">
          <h3 className="text-base font-semibold text-slate-100">{result.world_name}</h3>
          <p className="text-xs text-slate-400 leading-relaxed mt-1">{result.world_description}</p>
        </div>
      </div>

      {result.axiom && (
        <div className="rounded-lg border border-indigo-500/20 bg-indigo-500/5 px-3 py-2">
          <p className="text-[10px] uppercase tracking-wider text-indigo-400 mb-0.5">World axiom</p>
          <p className="text-xs text-slate-300 italic">{result.axiom}</p>
        </div>
      )}

      {result.entities.length > 0 && (
        <div className="space-y-1.5">
          <p className="text-[10px] uppercase tracking-wider text-slate-500">
            {result.committed} committed to canon
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5">
            {result.entities.map((e) => {
              const Icon = ENTITY_ICON[e.type] ?? Sparkles;
              return (
                <div key={e.name} className="flex items-start gap-2 rounded-lg bg-white/4 px-2.5 py-1.5">
                  <Icon className="w-3.5 h-3.5 text-cyan-400 flex-shrink-0 mt-0.5" />
                  <div className="min-w-0">
                    <p className="text-xs text-slate-200 truncate">{e.name}</p>
                    {e.want && <p className="text-[10px] text-slate-500 truncate">wants: {e.want}</p>}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {result.opening_scene && (
        <div className="rounded-lg border border-white/5 bg-black/20 px-3 py-2">
          <p className="text-[10px] uppercase tracking-wider text-amber-400 mb-0.5">Opening scene</p>
          <p className="text-xs text-slate-300 leading-relaxed">{result.opening_scene}</p>
        </div>
      )}

      {result.pc_concept && (
        <p className="text-xs text-slate-400">
          <span className="text-slate-500">Suggested character — </span>
          {result.pc_concept}
        </p>
      )}

      {result.errors.length > 0 && (
        <div className="flex items-start gap-2 text-[11px] text-amber-300/80">
          <AlertCircle className="w-3.5 h-3.5 flex-shrink-0 mt-px" />
          <span>{result.errors.join("; ")}</span>
        </div>
      )}

      <div className="flex flex-wrap gap-2 pt-1">
        <Link
          href={
            result.session_id
              ? `/play?session=${result.session_id}`
              : `/play?universe=${result.universe_id}&multiverse=${result.multiverse_id}`
          }
          className="btn-cyber justify-center text-sm py-2 px-4"
        >
          <Gamepad2 className="w-4 h-4" /> Play here now
        </Link>
        <Link
          href={`/worlds?universe=${result.universe_id}`}
          className="btn-ghost justify-center text-sm py-2 px-4 border border-white/10"
        >
          <Network className="w-4 h-4" /> Open in tree
        </Link>
      </div>
    </motion.div>
  );
}

export function QuickStartPanel() {
  const qc = useQueryClient();
  const { setWorld } = useWorldContext();
  const [seed, setSeed] = useState("");
  const [genre, setGenre] = useState("");
  const [tone, setTone] = useState("");
  const [name, setName] = useState("");
  const [startPlaying, setStartPlaying] = useState(true);

  const mut = useMutation({
    mutationFn: () =>
      forgeApi.quickWorld({
        seed: seed.trim(),
        genre: genre || undefined,
        tone: tone || undefined,
        name: name.trim() || undefined,
        start_playing: startPlaying,
      }),
    onSuccess: (result) => {
      qc.invalidateQueries({ queryKey: ["universes"] });
      qc.invalidateQueries({ queryKey: ["multiverses"] });
      // The freshly forged world becomes the active world everywhere (T-077)
      setWorld({
        multiverseId: result.multiverse_id,
        universeId: result.universe_id,
        universeLabel: result.world_name,
      });
    },
  });

  return (
    <div className="max-w-3xl mx-auto space-y-5">
      <div className="space-y-1">
        <h2 className="text-xl font-bold text-slate-100 flex items-center gap-2">
          <Wand2 className="w-5 h-5 text-purple-400" /> Quick Start
        </h2>
        <p className="text-sm text-slate-500">
          Describe a world in a sentence. MONITOR forges a small, playable setting — places,
          characters with wants, a world-truth, and an opening scene — ready to play in seconds.
          No rulebook required.
        </p>
      </div>

      <div className="glass rounded-2xl border border-purple-500/15 p-5 space-y-4">
        <div className="space-y-2">
          <label className="text-xs text-slate-500">Your seed</label>
          <textarea
            value={seed}
            onChange={(e) => setSeed(e.target.value)}
            rows={3}
            placeholder="A rain-soaked harbor city where the drowned barter for the memories they lost at sea…"
            className="input-cyber w-full resize-none text-sm"
          />
          <div className="flex flex-wrap gap-1.5">
            {SEED_EXAMPLES.map((ex) => (
              <button
                key={ex}
                onClick={() => setSeed(ex)}
                className="text-[10px] px-2 py-1 rounded-full border border-white/8 text-slate-500 hover:text-slate-300 hover:border-purple-500/30 transition-all text-left max-w-full truncate"
                title={ex}
              >
                {ex.slice(0, 48)}…
              </button>
            ))}
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="space-y-1.5">
            <label className="text-xs text-slate-500">Genre</label>
            <div className="flex flex-wrap gap-1.5">
              {GENRES.map((g) => (
                <button
                  key={g}
                  onClick={() => setGenre(genre === g ? "" : g)}
                  className={cn(
                    "text-[11px] px-2 py-1 rounded-full border transition-all capitalize",
                    genre === g
                      ? "bg-cyan-500/15 text-cyan-300 border-cyan-500/35"
                      : "border-white/10 text-slate-500 hover:text-slate-300",
                  )}
                >
                  {g}
                </button>
              ))}
            </div>
          </div>
          <div className="space-y-1.5">
            <label className="text-xs text-slate-500">Tone</label>
            <div className="flex flex-wrap gap-1.5">
              {TONES.map((t) => (
                <button
                  key={t}
                  onClick={() => setTone(tone === t ? "" : t)}
                  className={cn(
                    "text-[11px] px-2 py-1 rounded-full border transition-all capitalize",
                    tone === t
                      ? "bg-purple-500/15 text-purple-300 border-purple-500/35"
                      : "border-white/10 text-slate-500 hover:text-slate-300",
                  )}
                >
                  {t}
                </button>
              ))}
            </div>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="World name (optional)"
            className="input-cyber flex-1 min-w-[180px] text-sm"
          />
          <label className="flex items-center gap-2 text-xs text-slate-400 cursor-pointer">
            <input
              type="checkbox"
              checked={startPlaying}
              onChange={(e) => setStartPlaying(e.target.checked)}
              className="accent-cyan-500"
            />
            Start a session immediately
          </label>
        </div>

        <button
          onClick={() => mut.mutate()}
          disabled={seed.trim().length < 3 || mut.isPending}
          className="btn-cyber w-full justify-center py-2.5"
        >
          {mut.isPending ? (
            <>
              <Loader2 className="w-4 h-4 animate-spin" /> Forging your world…
            </>
          ) : (
            <>
              <Wand2 className="w-4 h-4" /> Forge world
            </>
          )}
        </button>

        {mut.isError && (
          <div className="flex items-start gap-2 text-xs text-red-300">
            <AlertCircle className="w-4 h-4 flex-shrink-0 mt-px" />
            <span>{mut.error instanceof Error ? mut.error.message : "World generation failed."}</span>
          </div>
        )}
      </div>

      <AnimatePresence>
        {mut.data && <ResultCard result={mut.data} />}
      </AnimatePresence>
    </div>
  );
}
