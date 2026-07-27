"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { Globe2, Loader2, X } from "lucide-react";
import { universesApi } from "@/lib/api";
import type { Universe } from "@/lib/types";
import { cn } from "@/lib/utils";

/**
 * Shared "new universe" form (F1-3b). Single source of truth used by the
 * Worlds hierarchy tab (inline panel) and the /forge/worlds/new wizard's
 * Blank method.
 */
export function CreateUniverseForm({
  multiverseId,
  onClose,
  onCreated,
}: {
  multiverseId: string;
  onClose: () => void;
  onCreated?: (universe: Universe) => void;
}) {
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [genre, setGenre] = useState("");
  const [desc, setDesc] = useState("");

  const mut = useMutation({
    mutationFn: () =>
      universesApi.createUniverse({
        name,
        multiverse_id: multiverseId,
        genre: genre || undefined,
        description: desc || undefined,
      }),
    onSuccess: (created) => {
      qc.invalidateQueries({ queryKey: ["universes"] });
      qc.invalidateQueries({ queryKey: ["multiverses"] });
      onCreated?.(created);
      onClose();
    },
  });

  const GENRES = ["Fantasy", "Sci-Fi", "Horror", "Cyberpunk", "Historical", "Modern", "Mystery", "Western", "Superhero"];

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.97 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0 }}
      className="glass rounded-2xl border border-cyan-500/20 p-5 space-y-4"
    >
      <div className="flex items-center justify-between">
        <p className="text-sm font-semibold text-slate-200">New Universe</p>
        <button onClick={onClose} className="text-slate-600 hover:text-slate-300">
          <X className="w-4 h-4" />
        </button>
      </div>

      <input
        className="input-cyber w-full"
        placeholder="Universe name…"
        value={name}
        onChange={(e) => setName(e.target.value)}
        autoFocus
      />

      <div>
        <p className="text-xs text-slate-600 mb-2">Genre</p>
        <div className="flex flex-wrap gap-2">
          {GENRES.map((g) => (
            <button
              key={g}
              onClick={() => setGenre(genre === g ? "" : g)}
              className={cn(
                "text-xs px-2.5 py-1 rounded-full border transition-all",
                genre === g
                  ? "bg-cyan-500/15 border-cyan-500/40 text-cyan-300"
                  : "border-white/10 text-slate-500 hover:border-white/20 hover:text-slate-300",
              )}
            >
              {g}
            </button>
          ))}
        </div>
      </div>

      <textarea
        className="input-cyber w-full resize-none"
        rows={2}
        placeholder="Short description (optional)"
        value={desc}
        onChange={(e) => setDesc(e.target.value)}
      />

      <button
        onClick={() => mut.mutate()}
        disabled={!name.trim() || mut.isPending}
        className="btn-cyber w-full justify-center"
      >
        {mut.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Globe2 className="w-4 h-4" />}
        Create Universe
      </button>
    </motion.div>
  );
}
