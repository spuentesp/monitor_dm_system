"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toneApi } from "@/lib/api";
import type { TagCategory, TagDefinition } from "@/lib/types";
import { cn } from "@/lib/utils";

/**
 * Tag Definitions tab (F3-4.3). CRUD over the tag registry, grouped by the
 * four tag categories. Built-in tags cannot be deleted and only accept
 * synonym/description updates (enforced by the backend too).
 */

const TAG_CATEGORIES: { id: TagCategory; label: string; hint: string }[] = [
  { id: "tone", label: "Tone", hint: "Narrative style (grim, whimsical, noir…)" },
  { id: "theme", label: "Theme", hint: "Recurring motifs (corruption, redemption…)" },
  { id: "style", label: "Style", hint: "Prose mechanics (terse, second_person…)" },
  { id: "concept", label: "Concept", hint: "Guiding principles (hope_is_earned…)" },
];

const inputCls =
  "bg-zinc-900 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-slate-200";

function parseSynonyms(raw: string): string[] {
  return raw
    .split(",")
    .map((t) => t.trim())
    .filter(Boolean);
}

export function TagDefinitionsPanel() {
  const qc = useQueryClient();
  const [category, setCategory] = useState<TagCategory>("tone");

  const tagsQ = useQuery({
    queryKey: ["tone", "tags", category],
    queryFn: () => toneApi.listTags({ category }),
  });

  const [newTag, setNewTag] = useState("");
  const [newSynonyms, setNewSynonyms] = useState("");
  const [newDescription, setNewDescription] = useState("");

  const [editingTag, setEditingTag] = useState<string | null>(null);
  const [editSynonyms, setEditSynonyms] = useState("");
  const [editDescription, setEditDescription] = useState("");

  const invalidate = () => qc.invalidateQueries({ queryKey: ["tone", "tags"] });

  const createM = useMutation({
    mutationFn: () =>
      toneApi.createTag({
        tag: newTag.trim().toLowerCase().replace(/\s+/g, "_"),
        category,
        synonyms: parseSynonyms(newSynonyms),
        description: newDescription.trim(),
      }),
    onSuccess: () => {
      invalidate();
      setNewTag("");
      setNewSynonyms("");
      setNewDescription("");
    },
  });

  const updateM = useMutation({
    mutationFn: (tag: string) =>
      toneApi.updateTag(tag, {
        synonyms: parseSynonyms(editSynonyms),
        description: editDescription.trim(),
      }),
    onSuccess: () => {
      invalidate();
      setEditingTag(null);
    },
  });

  const deleteM = useMutation({
    mutationFn: (tag: string) => toneApi.deleteTag(tag),
    onSuccess: invalidate,
  });

  const startEdit = (t: TagDefinition) => {
    setEditingTag(t.tag);
    setEditSynonyms(t.synonyms.join(", "));
    setEditDescription(t.description);
  };

  const tags = tagsQ.data?.tags ?? [];
  const active = TAG_CATEGORIES.find((c) => c.id === category)!;

  return (
    <div className="space-y-6 max-w-4xl">
      <div>
        <h2 className="text-lg font-bold text-slate-100">Tag Definitions</h2>
        <p className="text-sm text-slate-500 mt-1">
          The canonical tag registry. Synonyms normalize user-provided tags to
          the canonical name.
        </p>
      </div>

      {/* Category tabs */}
      <div className="flex items-center gap-1 border-b border-white/5">
        {TAG_CATEGORIES.map((c) => (
          <button
            key={c.id}
            onClick={() => {
              setCategory(c.id);
              setEditingTag(null);
            }}
            className={cn(
              "px-4 py-2 text-sm font-medium border-b-2 transition-all",
              category === c.id
                ? "border-cyan-500 text-cyan-300"
                : "border-transparent text-slate-500 hover:text-slate-300",
            )}
          >
            {c.label}
          </button>
        ))}
      </div>

      {/* Create form */}
      <div className="space-y-2">
        <p className="text-xs text-slate-500">{active.hint}</p>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-2 items-end">
          <input
            aria-label="New tag name"
            value={newTag}
            onChange={(e) => setNewTag(e.target.value)}
            placeholder="Tag name (e.g. grim_noir)"
            className={inputCls}
          />
          <input
            aria-label="New tag synonyms"
            value={newSynonyms}
            onChange={(e) => setNewSynonyms(e.target.value)}
            placeholder="Synonyms (comma separated)"
            className={inputCls}
          />
          <button
            onClick={() => createM.mutate()}
            disabled={!newTag.trim() || createM.isPending}
            className="px-3 py-2 rounded-lg bg-purple-600 hover:bg-purple-500 disabled:opacity-40 text-sm text-white"
          >
            Add tag
          </button>
          <input
            aria-label="New tag description"
            value={newDescription}
            onChange={(e) => setNewDescription(e.target.value)}
            placeholder="Description"
            className={`md:col-span-3 ${inputCls}`}
          />
        </div>
      </div>

      {/* List */}
      <div className="space-y-2">
        {tagsQ.isLoading && <p className="text-sm text-slate-500">Loading…</p>}
        {!tagsQ.isLoading && tags.length === 0 && (
          <p className="text-sm text-slate-500">No {active.label.toLowerCase()} tags yet.</p>
        )}
        {tags.map((t) => (
          <div
            key={t.tag}
            className="flex items-start justify-between gap-4 bg-zinc-900/60 border border-zinc-800 rounded-lg px-4 py-3"
          >
            {editingTag === t.tag ? (
              <div className="flex-1 grid grid-cols-1 md:grid-cols-3 gap-2 items-end">
                <input
                  aria-label="Edit synonyms"
                  value={editSynonyms}
                  onChange={(e) => setEditSynonyms(e.target.value)}
                  className={inputCls}
                />
                <input
                  aria-label="Edit description"
                  value={editDescription}
                  onChange={(e) => setEditDescription(e.target.value)}
                  className={`md:col-span-2 ${inputCls}`}
                />
                <div className="flex gap-2 md:col-span-3">
                  <button
                    onClick={() => updateM.mutate(t.tag)}
                    disabled={updateM.isPending}
                    className="px-3 py-2 rounded-lg bg-purple-600 hover:bg-purple-500 disabled:opacity-40 text-sm text-white"
                  >
                    Save
                  </button>
                  <button
                    onClick={() => setEditingTag(null)}
                    className="px-3 py-2 rounded-lg text-sm text-slate-400 hover:text-slate-200"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            ) : (
              <>
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-slate-100">{t.tag}</span>
                    {t.is_builtin && (
                      <span className="text-[10px] uppercase px-1.5 py-0.5 rounded bg-cyan-500/10 text-cyan-300 border border-cyan-500/30">
                        builtin
                      </span>
                    )}
                  </div>
                  {t.description && (
                    <p className="text-xs text-slate-400 mt-1">{t.description}</p>
                  )}
                  {t.synonyms.length > 0 && (
                    <div className="flex gap-1 mt-1 flex-wrap">
                      {t.synonyms.map((s) => (
                        <span
                          key={s}
                          className="text-[10px] px-1.5 py-0.5 rounded bg-white/5 text-slate-400"
                        >
                          {s}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
                <div className="flex items-center gap-3 flex-shrink-0">
                  <button
                    onClick={() => startEdit(t)}
                    className="text-xs text-slate-400 hover:text-slate-200"
                  >
                    Edit
                  </button>
                  {!t.is_builtin && (
                    <button
                      onClick={() => deleteM.mutate(t.tag)}
                      className="text-xs text-red-400 hover:text-red-300"
                    >
                      Delete
                    </button>
                  )}
                </div>
              </>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
