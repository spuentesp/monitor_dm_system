"use client";

import { Brain, Images, MessageCircle, MoreVertical, Palette, Sparkles, Trash2, Upload } from "lucide-react";
import { useState } from "react";
import { apiUrl } from "@/lib/api";
import { useDismissRef } from "@/lib/useDismissRef";
import type { StandaloneCharacter } from "@/lib/types";
import { cn } from "@/lib/utils";

function oneLine(text: string): string {
  return (text ?? "").split("\n").map((l) => l.trim()).find(Boolean) ?? "";
}

export function CharacterCardGrid({
  characters,
  onChat,
  onGeneratePortrait,
  onEditVisualIdentity,
  onVisualReferences,
  onDelete,
}: {
  characters: StandaloneCharacter[];
  onChat: (c: StandaloneCharacter) => void;
  onGeneratePortrait?: (c: StandaloneCharacter) => void;
  onEditVisualIdentity?: (c: StandaloneCharacter) => void;
  onVisualReferences?: (c: StandaloneCharacter) => void;
  onDelete: (c: StandaloneCharacter) => void;
}) {
  const [menuFor, setMenuFor] = useState<string | null>(null);
  // One open menu at a time — the ref is attached to the card that owns it.
  const menuRef = useDismissRef<HTMLDivElement>(() => setMenuFor(null), menuFor !== null);
  const [confirmDelete, setConfirmDelete] = useState<StandaloneCharacter | null>(null);

  if (characters.length === 0) {
    return (
      <div className="glass flex flex-col items-center justify-center gap-4 rounded-2xl border border-dashed border-purple-500/25 px-6 py-14 text-center">
        <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-purple-500/10 border border-purple-500/25 shadow-purple-glow">
          <Upload className="h-7 w-7 text-purple-400" />
        </div>
        <div>
          <p className="text-base font-semibold text-slate-200">No characters yet</p>
          <p className="mt-1 text-sm text-slate-500 max-w-sm">
            Import a SillyTavern card (JSON or PNG) to start chatting. Use the
            <span className="mx-1 inline-flex items-center gap-1 text-purple-300">
              <Upload className="h-3 w-3" /> Import card
            </span>
            button above.
          </p>
        </div>
        <a
          href="https://docs.charadex.io/character-cards"
          target="_blank"
          rel="noopener noreferrer"
          className="text-[11px] text-slate-600 hover:text-purple-300 transition-colors"
        >
          What is a character card? →
        </a>
      </div>
    );
  }

  return (
    <>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
      {characters.map((c) => (
        <div
          key={c.id}
          ref={menuFor === c.id ? menuRef : undefined}
          className="glass relative flex flex-col gap-3 rounded-2xl p-4"
        >
          <div className="flex items-start gap-3">
            {c.avatar_url ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={apiUrl(`/image/avatar/${c.id}`)}
                alt={c.name}
                className="h-12 w-12 flex-shrink-0 rounded-full border border-white/10 object-cover"
              />
            ) : (
              <div className="flex h-12 w-12 flex-shrink-0 items-center justify-center rounded-full bg-purple-500/15 text-sm font-bold text-purple-300">
                {c.name.slice(0, 2).toUpperCase()}
              </div>
            )}
            <div className="min-w-0 flex-1">
              <div className="truncate text-sm font-semibold text-slate-100">{c.name}</div>
              <div className="truncate text-[11px] text-slate-500">{oneLine(c.description) || "—"}</div>
            </div>
            <button
              onClick={() => setMenuFor(menuFor === c.id ? null : c.id)}
              aria-label={`Actions for ${c.name}`}
              className="text-slate-600 hover:text-slate-300"
            >
              <MoreVertical className="h-4 w-4" />
            </button>
          </div>

          {menuFor === c.id && (
            <div className="absolute right-3 top-12 z-10 w-44 rounded-lg border border-white/10 bg-slate-900/95 py-1 shadow-xl">
              {onGeneratePortrait && (
                <button
                  onClick={() => {
                    setMenuFor(null);
                    onGeneratePortrait(c);
                  }}
                  className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs text-slate-300 hover:bg-white/5"
                >
                  <Sparkles className="h-3 w-3 text-cyan-300" /> Generate portrait
                </button>
              )}
              {onEditVisualIdentity && (
                <button
                  onClick={() => {
                    setMenuFor(null);
                    onEditVisualIdentity(c);
                  }}
                  className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs text-slate-300 hover:bg-white/5"
                >
                  <Palette className="h-3 w-3 text-purple-300" /> Edit visual identity
                </button>
              )}
              {onVisualReferences && (
                <button
                  onClick={() => {
                    setMenuFor(null);
                    onVisualReferences(c);
                  }}
                  className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs text-slate-300 hover:bg-white/5"
                >
                  <Images className="h-3 w-3 text-cyan-300" /> Visual references
                </button>
              )}
              <button
                onClick={() => {
                  setMenuFor(null);
                  setConfirmDelete(c);
                }}
                className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs text-red-300 hover:bg-white/5"
              >
                <Trash2 className="h-3 w-3" /> Delete
              </button>
            </div>
          )}

          <div className="mt-auto flex items-center justify-between">
            <span
              className={cn(
                "flex items-center gap-1 rounded-md border px-2 py-0.5 text-[10px]",
                "border-purple-500/25 bg-purple-500/10 text-purple-300",
              )}
              title="Stored memories"
            >
              <Brain className="h-3 w-3" /> {c.memory_count}
            </span>
            <button
              onClick={() => onChat(c)}
              className="btn-cyber flex items-center gap-1.5 px-3 py-1.5 text-xs"
            >
              <MessageCircle className="h-3 w-3" /> Chat
            </button>
          </div>
        </div>
      ))}
      </div>

      {confirmDelete && (
        <div
          role="dialog"
          aria-label={`Delete ${confirmDelete.name}`}
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
        >
          <div className="glass w-full max-w-sm space-y-4 rounded-2xl border border-red-500/20 p-6">
            <h2 className="text-sm font-semibold text-slate-100">Delete {confirmDelete.name}?</h2>
            <p className="text-xs text-slate-400">
              This permanently removes {confirmDelete.name} and their memories. This can't be
              undone.
            </p>
            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setConfirmDelete(null)}
                className="btn-ghost px-3 py-1.5 text-xs"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => {
                  onDelete(confirmDelete);
                  setConfirmDelete(null);
                }}
                className="btn-cyber border-red-500/40 px-3 py-1.5 text-xs text-red-200"
              >
                Confirm
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
