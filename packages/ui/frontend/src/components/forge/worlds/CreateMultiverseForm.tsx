"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { Loader2, Plus, X } from "lucide-react";
import { universesApi } from "@/lib/api";
import type { Multiverse } from "@/lib/types";

/**
 * Shared "new multiverse" form (F1-3b). Single source of truth used by the
 * Worlds hierarchy tab (inline panel) and the /forge/worlds/new wizard's
 * Blank method.
 */
export function CreateMultiverseForm({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated?: (mv: Multiverse) => void;
}) {
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [desc, setDesc] = useState("");

  const mut = useMutation({
    mutationFn: () => universesApi.createMultiverse({ name, description: desc || undefined }),
    onSuccess: (created) => {
      qc.invalidateQueries({ queryKey: ["multiverses"] });
      onCreated?.(created);
      onClose();
    },
  });

  return (
    <motion.div
      initial={{ opacity: 0, y: -6 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -6 }}
      className="glass-dark rounded-xl border border-purple-500/20 p-4 space-y-3"
    >
      <div className="flex items-center justify-between">
        <p className="text-xs font-semibold text-purple-300">New Multiverse</p>
        <button onClick={onClose} aria-label="Close" className="text-slate-600 hover:text-slate-300">
          <X className="w-3.5 h-3.5" />
        </button>
      </div>
      <input
        className="input-cyber w-full"
        placeholder="Name…"
        value={name}
        onChange={(e) => setName(e.target.value)}
        autoFocus
      />
      <input
        className="input-cyber w-full"
        placeholder="Description (optional)"
        value={desc}
        onChange={(e) => setDesc(e.target.value)}
      />
      <button
        onClick={() => mut.mutate()}
        disabled={!name.trim() || mut.isPending}
        className="btn-cyber w-full justify-center"
      >
        {mut.isPending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Plus className="w-3.5 h-3.5" />}
        Create
      </button>
    </motion.div>
  );
}
