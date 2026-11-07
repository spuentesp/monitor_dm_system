"use client";

import { useCallback, useState } from "react";
import { motion } from "framer-motion";
import { X, Save, Loader2 } from "lucide-react";
import { useMutation } from "@tanstack/react-query";

import { characterTemplatesApi } from "@/lib/api";
import type { CharacterTemplate } from "@/lib/types";

/**
 * Create a portable character template (G-6 / P&F §6).
 *
 * A template is deliberately portable: concept, personality, voice and
 * backstory beats — no stats, no skills, no world binding. The world supplies
 * the mechanics when the character is instantiated.
 */
export function TemplateEditor({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated?: (template: CharacterTemplate) => void;
}) {
  const [name, setName] = useState("");
  const [concept, setConcept] = useState("");
  const [personality, setPersonality] = useState("");
  const [voice, setVoice] = useState("");
  const [backstoryBeats, setBackstoryBeats] = useState("");
  const [gmNotes, setGmNotes] = useState("");
  const [error, setError] = useState<string | null>(null);

  const createMutation = useMutation({
    mutationFn: (data: Parameters<typeof characterTemplatesApi.create>[0]) =>
      characterTemplatesApi.create(data),
    onSuccess: (template) => {
      onCreated?.(template);
      onClose();
    },
    onError: (err: unknown) => {
      setError(err instanceof Error ? err.message : "Could not create the template");
    },
  });

  const handleSubmit = useCallback(() => {
    if (!name.trim()) return;
    setError(null);
    createMutation.mutate({
      name: name.trim(),
      concept: concept.trim(),
      personality: personality.trim(),
      voice: voice.trim(),
      backstory_beats: backstoryBeats
        .split("\n")
        .map((beat) => beat.trim())
        .filter(Boolean),
      gm_notes: gmNotes.trim(),
    });
  }, [name, concept, personality, voice, backstoryBeats, gmNotes, createMutation]);

  const inputClass =
    "w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-slate-200 placeholder:text-slate-600 resize-none focus:outline-none focus:border-cyan-500/30";

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
        className="glass rounded-2xl border border-white/10 w-full max-w-lg p-6 space-y-5 max-h-[85vh] overflow-y-auto"
      >
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-sm font-semibold text-slate-200">New Character Template</h2>
            <p className="text-[10px] text-slate-500">
              Portable — no stats, no skills. The world supplies the mechanics.
            </p>
          </div>
          <button
            onClick={onClose}
            aria-label="Close"
            className="p-1 rounded-lg hover:bg-white/5 transition-all"
          >
            <X className="w-4 h-4 text-slate-400" />
          </button>
        </div>

        <div className="space-y-4">
          <div>
            <label className="text-[10px] uppercase tracking-wider text-slate-500 mb-1 block">
              Name
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Varys"
              className={inputClass}
            />
          </div>

          <div>
            <label className="text-[10px] uppercase tracking-wider text-slate-500 mb-1 block">
              Concept
            </label>
            <textarea
              value={concept}
              onChange={(e) => setConcept(e.target.value)}
              placeholder="A spymaster who is never where you expect"
              rows={2}
              className={inputClass}
            />
          </div>

          <div>
            <label className="text-[10px] uppercase tracking-wider text-slate-500 mb-1 block">
              Personality
            </label>
            <textarea
              value={personality}
              onChange={(e) => setPersonality(e.target.value)}
              placeholder="Traits, mannerisms, loyalties..."
              rows={2}
              className={inputClass}
            />
          </div>

          <div>
            <label className="text-[10px] uppercase tracking-wider text-slate-500 mb-1 block">
              Voice
            </label>
            <textarea
              value={voice}
              onChange={(e) => setVoice(e.target.value)}
              placeholder="How they speak — tone, cadence, verbal tics..."
              rows={2}
              className={inputClass}
            />
          </div>

          <div>
            <label className="text-[10px] uppercase tracking-wider text-slate-500 mb-1 block">
              Backstory Beats
            </label>
            <textarea
              value={backstoryBeats}
              onChange={(e) => setBackstoryBeats(e.target.value)}
              placeholder={"One beat per line\nLost a city to a bargain\nNever pays his debts"}
              rows={3}
              className={inputClass}
            />
            <p className="text-[10px] text-slate-600 mt-1">
              Beats pre-fill Session Zero instead of re-interviewing the player.
            </p>
          </div>

          <div>
            <label className="text-[10px] uppercase tracking-wider text-amber-500/70 mb-1 block">
              Author&apos;s Note (GM Notes)
            </label>
            <textarea
              value={gmNotes}
              onChange={(e) => setGmNotes(e.target.value)}
              placeholder="Hidden instructions for the AI — not shown to players"
              rows={2}
              className="w-full bg-amber-500/5 border border-amber-500/10 rounded-lg px-3 py-2 text-sm text-slate-200 placeholder:text-slate-600 resize-none focus:outline-none focus:border-amber-500/30"
            />
          </div>

          {error && (
            <p className="text-[10px] text-red-400 border border-red-500/20 bg-red-500/5 rounded-lg px-3 py-2">
              {error}
            </p>
          )}
        </div>

        <div className="flex items-center justify-end gap-3 pt-2 border-t border-white/5">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-lg text-xs text-slate-400 hover:text-slate-200 hover:bg-white/5 transition-all"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            aria-label="Save template"
            disabled={!name.trim() || createMutation.isPending}
            className="btn-cyber gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {createMutation.isPending ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <Save className="w-3.5 h-3.5" />
            )}
            Create template
          </button>
        </div>
      </motion.div>
    </motion.div>
  );
}
