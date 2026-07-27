"use client";

import { useCallback, useState } from "react";
import { motion } from "framer-motion";
import { X, Trash2, Brain, AlertTriangle, Loader2 } from "lucide-react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";

import { entitiesApi } from "@/lib/api";
import { cn, formatRelativeTime } from "@/lib/utils";
import { ENTITY_KEYS } from "@/lib/query-keys";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface MemoryInspectorProps {
  characterId: string;
  onClose: () => void;
}

// ---------------------------------------------------------------------------
// MemoryInspector
// ---------------------------------------------------------------------------

export function MemoryInspector({ characterId, onClose }: MemoryInspectorProps) {
  const qc = useQueryClient();
  const [minImportance, setMinImportance] = useState(0);
  const [showClearConfirm, setShowClearConfirm] = useState(false);

  // Fetch memories
  const { data, isLoading } = useQuery({
    queryKey: ENTITY_KEYS.characterMemories(characterId),
    queryFn: () =>
      entitiesApi.getCharacterMemories(characterId, {
        min_importance: minImportance,
        limit: 50,
      }),
  });

  const memories = data?.memories ?? [];
  const total = data?.total ?? 0;

  // Clear all memories
  const clearMutation = useMutation({
    mutationFn: () => entitiesApi.clearCharacterMemories(characterId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ENTITY_KEYS.characterMemories(characterId) });
      setShowClearConfirm(false);
    },
  });

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <motion.div
        initial={{ opacity: 0, scale: 0.95, y: 10 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.95, y: 10 }}
        className="glass rounded-2xl border border-white/10 w-full max-w-md p-6 space-y-4"
      >
        {/* Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 text-slate-200">
            <Brain className="w-4 h-4 text-purple-400" />
            <h2 className="text-sm font-semibold">Memories</h2>
            <span className="text-[10px] text-slate-500">{total} total</span>
          </div>
          <button onClick={onClose} aria-label="Close" className="p-1 rounded-lg hover:bg-white/5 transition-all">
            <X className="w-4 h-4 text-slate-400" />
          </button>
        </div>

        {/* Importance filter */}
        <div className="flex items-center gap-3">
          <label className="text-[10px] uppercase tracking-wider text-slate-500 flex-shrink-0">
            Min importance
          </label>
          <input
            type="range"
            min={0}
            max={1}
            step={0.1}
            value={minImportance}
            onChange={(e) => setMinImportance(parseFloat(e.target.value))}
            className="flex-1 accent-purple-400"
          />
          <span className="text-xs text-slate-400 w-8 text-right">
            {minImportance.toFixed(1)}
          </span>
        </div>

        {/* Memory list */}
        <div className="max-h-[50vh] overflow-y-auto space-y-2">
          {isLoading ? (
            <div className="flex items-center justify-center h-24 text-slate-600 text-xs">
              <Loader2 className="w-4 h-4 animate-spin mr-2" />
              Loading…
            </div>
          ) : memories.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-24 text-center space-y-2">
              <Brain className="w-8 h-8 text-slate-700" />
              <p className="text-xs text-slate-600">No memories found</p>
            </div>
          ) : (
            memories.map((mem) => (
              <div
                key={mem.id}
                className="p-3 rounded-xl bg-white/5 border border-white/5 space-y-1.5"
              >
                <p className="text-xs text-slate-300 leading-relaxed">{mem.text}</p>
                <div className="flex items-center justify-between">
                  <span className="text-[10px] text-slate-600">
                    {formatRelativeTime(mem.created_at)}
                  </span>
                  <span
                    className={cn(
                      "px-1.5 py-0.5 rounded text-[9px] font-medium",
                      mem.importance >= 0.7
                        ? "bg-purple-500/15 text-purple-300"
                        : mem.importance >= 0.4
                          ? "bg-cyan-500/15 text-cyan-300"
                          : "bg-white/5 text-slate-500",
                    )}
                  >
                    {mem.importance.toFixed(2)}
                  </span>
                </div>
              </div>
            ))
          )}
        </div>

        {/* Clear all */}
        <div className="pt-2 border-t border-white/5">
          {!showClearConfirm ? (
            <button
              onClick={() => setShowClearConfirm(true)}
              disabled={total === 0}
              className={cn(
                "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs transition-all",
                total === 0
                  ? "text-slate-700 cursor-not-allowed"
                  : "text-red-400 hover:bg-red-500/10 border border-red-500/20",
              )}
            >
              <Trash2 className="w-3 h-3" />
              Clear All Memories
            </button>
          ) : (
            <div className="flex items-center gap-3">
              <AlertTriangle className="w-4 h-4 text-red-400 flex-shrink-0" />
              <p className="text-xs text-slate-400 flex-1">
                Permanently delete all {total} memories?
              </p>
              <button
                onClick={() => clearMutation.mutate()}
                disabled={clearMutation.isPending}
                className="px-3 py-1.5 rounded-lg text-xs bg-red-500/15 text-red-300 border border-red-500/20 hover:bg-red-500/25 transition-all"
              >
                {clearMutation.isPending ? "Deleting…" : "Yes, delete"}
              </button>
              <button
                onClick={() => setShowClearConfirm(false)}
                className="px-3 py-1.5 rounded-lg text-xs text-slate-400 hover:text-slate-200 hover:bg-white/5 transition-all"
              >
                Cancel
              </button>
            </div>
          )}
        </div>
      </motion.div>
    </motion.div>
  );
}