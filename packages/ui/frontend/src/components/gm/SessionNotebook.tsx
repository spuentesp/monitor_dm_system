"use client";

import { useEffect, useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { motion, AnimatePresence } from "framer-motion";
import { Check, Loader2, Upload } from "lucide-react";
import { gmApi, ingestApi } from "@/lib/api";
import { cn } from "@/lib/utils";

export function SessionNotebook({
  universeId,
  multiverseId,
  storyId,
}: {
  universeId: string | null;
  multiverseId?: string | null;
  storyId?: string | null;
}) {
  const [notes, setNotes] = useState("");
  const [saved, setSaved] = useState(false);
  const [ingestStatus, setIngestStatus] = useState<"idle" | "pending" | "done" | "error">("idle");

  // P2.3 — server-backed scratchpad (replaces localStorage).
  // Hydrate from the API when the active universe changes; skip the query
  // when no universe is selected.
  const notesQuery = useQuery({
    queryKey: ["gm-notes", universeId],
    queryFn: () => gmApi.getNotes(universeId!),
    enabled: !!universeId,
    staleTime: 30_000,
  });

  useEffect(() => {
    if (notesQuery.data) setNotes(notesQuery.data.content);
  }, [notesQuery.data?.updated_at, notesQuery.data?.content]);

  // Debounced autosave: fire on every keystroke, but coalesce to one PUT
  // per 1.5s of idle. Skip when the field is empty (no row to write).
  const upsertNotes = useMutation({
    mutationFn: async (content: string) => gmApi.upsertNotes(universeId!, content),
    onSuccess: () => {
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    },
  });

  useEffect(() => {
    if (!universeId) return;
    if (notes === notesQuery.data?.content) return; // no change
    const handle = setTimeout(() => {
      if (notes.trim().length > 0) {
        upsertNotes.mutate(notes);
      }
    }, 1500);
    return () => clearTimeout(handle);
  }, [notes, universeId, notesQuery.data?.content]);

  const ingestNotes = useMutation({
    mutationFn: async () => {
      const blob = new Blob([notes], { type: "text/plain" });
      const file = new File([blob], "session-notes.txt", { type: "text/plain" });
      return ingestApi.uploadSource(file, {
        scan_type: "full",
        analysis_layers: ["axioms", "entities", "lore"],
        multiverse_id: multiverseId ?? undefined,
        story_id: storyId ?? undefined,
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
          {upsertNotes.isPending && (
            <motion.span initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="text-xs text-slate-500 flex items-center gap-1">
              <Loader2 className="w-3 h-3 animate-spin" /> Saving…
            </motion.span>
          )}
        </AnimatePresence>
        <button
          onClick={() => ingestNotes.mutate()}
          disabled={!notes.trim() || ingestNotes.isPending}
          className={cn("btn-ghost text-xs py-0.5 px-2 max-xl:min-h-11", !notes.trim() && "opacity-40 cursor-not-allowed")}
          title="Ingest notes into the world knowledge base. Proposals land in Forge → Review."
        >
          {ingestNotes.isPending ? <Loader2 className="w-3 h-3 animate-spin" /> : <Upload className="w-3 h-3" />} Ingest
        </button>
        <span data-testid="ingest-hint" className="text-[10px] text-slate-700">
          Proposals land in Forge → Review
        </span>
      </div>

      {/* Textarea */}
      <textarea
        data-testid="session-notebook-input"
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
