"use client";

import { useCallback, useState } from "react";
import { motion } from "framer-motion";
import { X, Save, Loader2, User } from "lucide-react";
import { useMutation } from "@tanstack/react-query";

import { entitiesApi } from "@/lib/api";
import type { StandaloneCharacter } from "@/lib/types";
import { cn } from "@/lib/utils";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface CharacterEditorProps {
  /** If provided, edit this character; otherwise create new */
  character: StandaloneCharacter | null;
  onClose: () => void;
}

// ---------------------------------------------------------------------------
// CharacterEditor
// ---------------------------------------------------------------------------

export function CharacterEditor({ character, onClose }: CharacterEditorProps) {
  const isEdit = !!character;

  const [name, setName] = useState(character?.name ?? "");
  const [description, setDescription] = useState(character?.description ?? "");
  const [avatarUrl, setAvatarUrl] = useState(character?.avatar_url ?? "");
  const [personality, setPersonality] = useState(character?.personality ?? "");
  const [gmNotes, setGmNotes] = useState(character?.gm_notes ?? "");
  const [firstMessage, setFirstMessage] = useState(character?.first_message ?? "");
  const [isOocPersona, setIsOocPersona] = useState(character?.is_ooc_persona ?? false);

  const createMutation = useMutation({
    mutationFn: (data: Parameters<typeof entitiesApi.createStandaloneCharacter>[0]) =>
      entitiesApi.createStandaloneCharacter(data),
    onSuccess: onClose,
  });

  const updateMutation = useMutation({
    mutationFn: (data: { id: string; body: Partial<StandaloneCharacter> }) =>
      entitiesApi.updateStandaloneCharacter(data.id, data.body as Record<string, unknown> as Omit<StandaloneCharacter, "id" | "created_at" | "updated_at" | "memory_count">),
    onSuccess: onClose,
  });

  const isPending = createMutation.isPending || updateMutation.isPending;

  const handleSubmit = useCallback(() => {
    if (!name.trim()) return;

    if (isEdit && character) {
      updateMutation.mutate({
        id: character.id,
        body: {
          name: name.trim(),
          description,
          avatar_url: avatarUrl || null,
          personality,
          gm_notes: gmNotes,
          first_message: isOocPersona ? firstMessage : undefined,
          is_ooc_persona: isOocPersona,
        } as unknown as Omit<StandaloneCharacter, "id" | "created_at" | "updated_at" | "memory_count">,
      });
    } else {
      createMutation.mutate({
        name: name.trim(),
        description,
        avatar_url: avatarUrl || null,
        personality,
        gm_notes: gmNotes,
        first_message: isOocPersona ? firstMessage : undefined,
        is_ooc_persona: isOocPersona,
      });
    }
  }, [
    name, description, avatarUrl, personality, gmNotes, firstMessage, isOocPersona,
    isEdit, character, createMutation, updateMutation,
  ]);

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
        className="glass rounded-2xl border border-white/10 w-full max-w-lg p-6 space-y-5"
      >
        {/* Header */}
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-slate-200">
            {isEdit ? "Edit Character" : "Create Character"}
          </h2>
          <button onClick={onClose} className="p-1 rounded-lg hover:bg-white/5 transition-all">
            <X className="w-4 h-4 text-slate-400" />
          </button>
        </div>

        <div className="space-y-4 max-h-[60vh] overflow-y-auto pr-1">
          {/* Avatar preview + URL */}
          <div className="flex items-center gap-4">
            <div className="w-14 h-14 rounded-xl bg-white/5 border border-white/10 flex items-center justify-center flex-shrink-0 overflow-hidden">
              {avatarUrl ? (
                <img src={avatarUrl} alt="Avatar" className="w-full h-full object-cover" />
              ) : (
                <User className="w-6 h-6 text-slate-500" />
              )}
            </div>
            <input
              type="text"
              value={avatarUrl}
              onChange={(e) => setAvatarUrl(e.target.value)}
              placeholder="Avatar URL (optional)"
              className="flex-1 bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-xs text-slate-200 placeholder:text-slate-600 focus:outline-none focus:border-cyan-500/30"
            />
          </div>

          {/* Name */}
          <div>
            <label className="text-[10px] uppercase tracking-wider text-slate-500 mb-1 block">
              Name *
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Character name"
              className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-slate-200 placeholder:text-slate-600 focus:outline-none focus:border-cyan-500/30"
            />
          </div>

          {/* Description */}
          <div>
            <label className="text-[10px] uppercase tracking-wider text-slate-500 mb-1 block">
              Description
            </label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Physical appearance, background, role..."
              rows={3}
              className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-slate-200 placeholder:text-slate-600 resize-none focus:outline-none focus:border-cyan-500/30"
            />
          </div>

          {/* Personality */}
          <div>
            <label className="text-[10px] uppercase tracking-wider text-slate-500 mb-1 block">
              Personality
            </label>
            <textarea
              value={personality}
              onChange={(e) => setPersonality(e.target.value)}
              placeholder="Traits, mannerisms, speech patterns..."
              rows={2}
              className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-slate-200 placeholder:text-slate-600 resize-none focus:outline-none focus:border-cyan-500/30"
            />
          </div>

          {/* GM Notes / Author's Note */}
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

          {/* OOC Persona toggle */}
          <div className="flex items-center justify-between">
            <div>
              <label className="text-xs text-slate-300 block">AI Persona (OOC mode)</label>
              <p className="text-[10px] text-slate-600">No memory/world context — bare character card only</p>
            </div>
            <button
              onClick={() => setIsOocPersona(!isOocPersona)}
              className={cn(
                "relative w-9 h-5 rounded-full transition-all",
                isOocPersona ? "bg-amber-500/30" : "bg-white/10",
              )}
            >
              <span
                className={cn(
                  "absolute top-0.5 w-4 h-4 rounded-full transition-all",
                  isOocPersona ? "left-[18px] bg-amber-400" : "left-0.5 bg-slate-500",
                )}
              />
            </button>
          </div>

          {/* First Message (OOC persona) */}
          {isOocPersona && (
            <div>
              <label className="text-[10px] uppercase tracking-wider text-slate-500 mb-1 block">
                First Message
              </label>
              <textarea
                value={firstMessage}
                onChange={(e) => setFirstMessage(e.target.value)}
                placeholder="Opening message when chat starts"
                rows={2}
                className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-slate-200 placeholder:text-slate-600 resize-none focus:outline-none focus:border-cyan-500/30"
              />
            </div>
          )}
        </div>

        {/* Actions */}
        <div className="flex items-center justify-end gap-3 pt-2 border-t border-white/5">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-lg text-xs text-slate-400 hover:text-slate-200 hover:bg-white/5 transition-all"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={!name.trim() || isPending}
            className={cn(
              "btn-cyber gap-2",
              (!name.trim() || isPending) && "opacity-50 cursor-not-allowed",
            )}
          >
            {isPending ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <Save className="w-3.5 h-3.5" />
            )}
            {isEdit ? "Save" : "Create"}
          </button>
        </div>
      </motion.div>
    </motion.div>
  );
}