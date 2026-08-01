"use client";

import { useCallback, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Plus,
  Sparkles,
  User,
  MoreVertical,
  Trash2,
  Brain,
  Import,
  BookOpen,
  Loader2,
  Upload,
} from "lucide-react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";

import { entitiesApi } from "@/lib/api";
import type { StandaloneCharacter } from "@/lib/types";
import { cn, truncate } from "@/lib/utils";
import { ENTITY_KEYS } from "@/lib/query-keys";
import { useNotify } from "@/components/NotificationProvider";

import { CharacterEditor } from "./CharacterEditor";
import { MemoryInspector } from "./MemoryInspector";
import { LorebookEditor } from "@/components/lorebook/LorebookEditor";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface CharacterPanelProps {
  /** Currently selected character ID */
  selectedId: string | null;
  /** Called when a character is selected */
  onSelect: (id: string | null, character: StandaloneCharacter | null) => void;
  /** Current chat mode — influences visual state */
  chatMode: "ic" | "ooc";
  /** Called when user toggles OOC/IC */
  onChatModeChange: (mode: "ic" | "ooc") => void;
}

// ---------------------------------------------------------------------------
// CharacterPanel
// ---------------------------------------------------------------------------

export function CharacterPanel({
  selectedId,
  onSelect,
  chatMode,
  onChatModeChange,
}: CharacterPanelProps) {
  const qc = useQueryClient();
  const [showEditor, setShowEditor] = useState(false);
  const [editingCharacter, setEditingCharacter] = useState<StandaloneCharacter | null>(null);
  const [contextMenuId, setContextMenuId] = useState<string | null>(null);
  const [showMemory, setShowMemory] = useState<string | null>(null);
  const [showLorebook, setShowLorebook] = useState<string | null>(null);
  const cardInputRef = useRef<HTMLInputElement>(null);
  const { notify } = useNotify();

  // SillyTavern/Tavern card import (chara_card_v2 JSON or PNG)
  const importCard = useMutation({
    mutationFn: (file: File) => entitiesApi.importCharacterCard(file),
    onSuccess: (char) => {
      qc.invalidateQueries({ queryKey: ENTITY_KEYS.standaloneCharacters() });
      onSelect(char.id, char);
      notify("info", `Imported “${char.name}”.`);
    },
    onError: (e: unknown) =>
      notify("error", e instanceof Error ? e.message : "Card import failed."),
  });

  // Fetch characters
  const { data: characters = [], isLoading } = useQuery({
    queryKey: ENTITY_KEYS.standaloneCharacters(),
    queryFn: () => entitiesApi.listStandaloneCharacters({ limit: 100 }),
  });

  // Delete character
  const deleteMutation = useMutation({
    mutationFn: (id: string) => entitiesApi.deleteStandaloneCharacter(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ENTITY_KEYS.standaloneCharacters() });
      if (selectedId) onSelect(null, null);
    },
  });

  const handleSelect = useCallback(
    (char: StandaloneCharacter) => {
      if (selectedId === char.id) {
        onSelect(null, null);
      } else {
        onSelect(char.id, char);
      }
    },
    [selectedId, onSelect],
  );

  const handleEdit = useCallback((char: StandaloneCharacter) => {
    setEditingCharacter(char);
    setShowEditor(true);
  }, []);

  const handleCreate = useCallback(() => {
    setEditingCharacter(null);
    setShowEditor(true);
  }, []);

  const handleEditorClose = useCallback(() => {
    setShowEditor(false);
    setEditingCharacter(null);
    qc.invalidateQueries({ queryKey: ENTITY_KEYS.standaloneCharacters() });
  }, [qc]);

  return (
    <div className="glass rounded-2xl border border-white/5 p-4 space-y-3 h-full flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-slate-200">
          <Sparkles className="w-4 h-4 text-purple-400" />
          <h2 className="text-sm font-semibold">Characters</h2>
        </div>
        <div className="flex items-center gap-1.5">
          <input
            ref={cardInputRef}
            type="file" aria-label="Upload character card file"
            accept=".json,.png"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) importCard.mutate(f);
              e.target.value = "";
            }}
          />
          <button
            onClick={() => cardInputRef.current?.click()}
            disabled={importCard.isPending}
            className="p-1.5 rounded-lg border border-purple-500/20 text-purple-300 hover:bg-purple-500/10 transition-all disabled:opacity-50"
            title="Import a SillyTavern / Tavern character card (JSON or PNG)"
          >
            {importCard.isPending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Upload className="w-3.5 h-3.5" />}
          </button>
          <button
            onClick={handleCreate}
            className="p-1.5 rounded-lg border border-cyan-500/20 text-cyan-400 hover:bg-cyan-500/10 transition-all"
            title="Create character"
          >
            <Plus className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Chat Mode Toggle */}
      <div className="flex items-center gap-2">
        <button
          onClick={() => onChatModeChange("ic")}
          className={cn(
            "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all",
            chatMode === "ic"
              ? "bg-emerald-500/15 text-emerald-300 border border-emerald-500/30"
              : "text-slate-500 border border-white/5 hover:text-slate-300",
          )}
        >
          <span className={cn("w-1.5 h-1.5 rounded-full", chatMode === "ic" ? "bg-emerald-400" : "bg-slate-600")} />
          In-Character
        </button>
        <button
          onClick={() => onChatModeChange("ooc")}
          className={cn(
            "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all",
            chatMode === "ooc"
              ? "bg-amber-500/15 text-amber-300 border border-amber-500/30"
              : "text-slate-500 border border-white/5 hover:text-slate-300",
          )}
        >
          <span className={cn("w-1.5 h-1.5 rounded-full", chatMode === "ooc" ? "bg-amber-400" : "bg-slate-600")} />
          Out-of-Character
        </button>
      </div>

      {/* Character List */}
      <div className="flex-1 overflow-y-auto space-y-1.5 min-h-0">
        {isLoading ? (
          <div className="flex items-center justify-center h-24 text-slate-600 text-xs">
            Loading…
          </div>
        ) : characters.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-24 text-center space-y-2">
            <User className="w-8 h-8 text-slate-700" />
            <p className="text-xs text-slate-600">No characters yet</p>
            <button
              onClick={handleCreate}
              className="text-[10px] text-cyan-400 hover:text-cyan-300 transition-colors"
            >
              Create one →
            </button>
          </div>
        ) : (
          characters.map((char) => (
            <div key={char.id} className="relative group">
              <button
                onClick={() => handleSelect(char)}
                className={cn(
                  "w-full flex items-center gap-2.5 px-3 py-2 pr-8 rounded-xl text-left transition-all",
                  selectedId === char.id
                    ? "bg-purple-500/10 border border-purple-500/20 text-slate-100"
                    : "text-slate-400 hover:bg-white/5 hover:text-slate-200 border border-transparent",
                )}
              >
                {/* Avatar */}
                <div className="w-8 h-8 rounded-lg bg-white/5 border border-white/10 flex items-center justify-center flex-shrink-0 overflow-hidden">
                  {char.avatar_url ? (
                    <img
                      src={char.avatar_url}
                      alt={char.name}
                      className="w-full h-full object-cover"
                    />
                  ) : (
                    <User className="w-4 h-4 text-slate-500" />
                  )}
                </div>

                <div className="flex-1 min-w-0">
                  <p className="text-xs font-semibold truncate">{char.name}</p>
                  <p className="text-[10px] text-slate-500 truncate">
                    {char.is_ooc_persona ? "AI Persona" : truncate(char.description || "No description", 40)}
                  </p>
                </div>

                {/* OOC badge */}
                {char.is_ooc_persona && (
                  <span className="px-1.5 py-0.5 rounded text-[9px] bg-amber-500/15 text-amber-300 border border-amber-500/20 flex-shrink-0">
                    OOC
                  </span>
                )}
              </button>

              {/* Context menu trigger — sibling of the card button, not a
                  descendant: nested <button> is invalid HTML and breaks
                  hydration. */}
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  setContextMenuId(contextMenuId === char.id ? null : char.id);
                }}
                className="absolute right-2 top-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100 p-1 rounded hover:bg-white/10 transition-all flex-shrink-0"
              >
                <MoreVertical className="w-3 h-3 text-slate-500" />
              </button>

              {/* Context menu */}
              <AnimatePresence>
                {contextMenuId === char.id && (
                  <motion.div
                    initial={{ opacity: 0, scale: 0.95 }}
                    animate={{ opacity: 1, scale: 1 }}
                    exit={{ opacity: 0, scale: 0.95 }}
                    className="absolute right-2 top-full z-50 glass rounded-xl border border-white/10 p-1.5 min-w-[140px] space-y-0.5"
                  >
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        handleEdit(char);
                        setContextMenuId(null);
                      }}
                      className="w-full text-left px-3 py-1.5 rounded-lg text-xs text-slate-300 hover:bg-white/5 transition-all flex items-center gap-2"
                    >
                      <Sparkles className="w-3 h-3" /> Edit
                    </button>
                    {char.entity_id && (
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          setShowMemory(char.id);
                          setContextMenuId(null);
                        }}
                        className="w-full text-left px-3 py-1.5 rounded-lg text-xs text-slate-300 hover:bg-white/5 transition-all flex items-center gap-2"
                      >
                        <Brain className="w-3 h-3" /> Memories
                      </button>
                    )}
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        setShowLorebook(char.id);
                        setContextMenuId(null);
                      }}
                      className="w-full text-left px-3 py-1.5 rounded-lg text-xs text-slate-300 hover:bg-white/5 transition-all flex items-center gap-2"
                    >
                      <BookOpen className="w-3 h-3" /> Lorebook
                    </button>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        deleteMutation.mutate(char.id);
                        setContextMenuId(null);
                      }}
                      className="w-full text-left px-3 py-1.5 rounded-lg text-xs text-red-300 hover:bg-red-500/10 transition-all flex items-center gap-2"
                    >
                      <Trash2 className="w-3 h-3" /> Delete
                    </button>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          ))
        )}
      </div>

      {/* Character Editor Modal */}
      <AnimatePresence>
        {showEditor && (
          <CharacterEditor
            character={editingCharacter}
            onClose={handleEditorClose}
          />
        )}
      </AnimatePresence>

      {/* Memory Inspector Modal */}
      <AnimatePresence>
        {showMemory && (
          <MemoryInspector
            characterId={showMemory}
            onClose={() => setShowMemory(null)}
          />
        )}
      </AnimatePresence>

      {/* Lorebook Editor Modal */}
      <AnimatePresence>
        {showLorebook && (
          <LorebookEditor
            characterId={showLorebook}
            onClose={() => setShowLorebook(null)}
          />
        )}
      </AnimatePresence>
    </div>
  );
}