"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toneApi } from "@/lib/api";
import type { ToneProfile } from "@/lib/types";
import { TagAutocompleteInput } from "./TagAutocompleteInput";

/**
 * Tone Profiles tab (CF-7). Reusable narration instructions matched by
 * trigger tags. Lifted from app/settings/page.tsx into Forge → Style
 * (F3-4.1 / F1-5a); the settings tone tab is now just a link here.
 */

// Categories per the backend schema docstring (narrative, genre, mood,
// pacing) plus "custom", which the pre-lift UI hardcoded on create.
const CATEGORIES = ["custom", "narrative", "genre", "mood", "pacing"] as const;
const LANGUAGES = ["en", "es", "fr", "de", "it", "pt"] as const;

const inputCls =
  "bg-zinc-900 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-slate-200";

function parseTags(raw: string): string[] {
  return raw
    .split(",")
    .map((t) => t.trim())
    .filter(Boolean);
}

export function ToneTab() {
  const qc = useQueryClient();
  const profilesQ = useQuery({
    queryKey: ["tone", "profiles"],
    queryFn: () => toneApi.listProfiles(),
  });
  const librariesQ = useQuery({
    queryKey: ["tone", "libraries"],
    queryFn: () => toneApi.listLibraries(),
  });

  const [name, setName] = useState("");
  const [instruction, setInstruction] = useState("");
  const [tags, setTags] = useState("");
  const [category, setCategory] = useState<string>("custom");
  const [language, setLanguage] = useState<string>("en");

  const [editingId, setEditingId] = useState<string | null>(null);
  const [editName, setEditName] = useState("");
  const [editInstruction, setEditInstruction] = useState("");
  const [editTags, setEditTags] = useState("");
  const [editCategory, setEditCategory] = useState<string>("custom");
  const [editLanguage, setEditLanguage] = useState<string>("en");

  const createM = useMutation({
    mutationFn: () =>
      toneApi.createProfile({
        name,
        description: name,
        instruction,
        trigger_tags: parseTags(tags),
        category,
        language,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["tone", "profiles"] });
      setName("");
      setInstruction("");
      setTags("");
      setCategory("custom");
      setLanguage("en");
    },
  });

  const updateM = useMutation({
    mutationFn: (id: string) =>
      toneApi.updateProfile(id, {
        name: editName,
        description: editName,
        instruction: editInstruction,
        trigger_tags: parseTags(editTags),
        category: editCategory,
        language: editLanguage,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["tone", "profiles"] });
      setEditingId(null);
    },
  });

  const deleteM = useMutation({
    mutationFn: (id: string) => toneApi.deleteProfile(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["tone", "profiles"] }),
  });

  const startEdit = (p: ToneProfile) => {
    setEditingId(p.profile_id);
    setEditName(p.name);
    setEditInstruction(p.instruction);
    setEditTags(p.trigger_tags.join(", "));
    setEditCategory(p.category || "custom");
    setEditLanguage(p.language || "en");
  };

  const profiles = profilesQ.data?.profiles ?? [];
  const libraries = librariesQ.data?.libraries ?? [];

  return (
    <div className="space-y-8 max-w-4xl">
      <div>
        <h2 className="text-lg font-bold text-slate-100">Tone Profiles</h2>
        <p className="text-sm text-slate-500 mt-1">
          Reusable narration instructions matched by trigger tags.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-2 items-end">
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Profile name"
          className={inputCls}
        />
        <TagAutocompleteInput
          value={tags}
          onChange={setTags}
          placeholder="Trigger tags (comma separated)"
          className={inputCls}
        />
        <button
          onClick={() => createM.mutate()}
          disabled={!name.trim() || !instruction.trim() || createM.isPending}
          className="px-3 py-2 rounded-lg bg-purple-600 hover:bg-purple-500 disabled:opacity-40 text-sm text-white"
        >
          Add profile
        </button>
        <select
          aria-label="Category"
          value={category}
          onChange={(e) => setCategory(e.target.value)}
          className={inputCls}
        >
          {CATEGORIES.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
        <select
          aria-label="Language"
          value={language}
          onChange={(e) => setLanguage(e.target.value)}
          className={inputCls}
        >
          {LANGUAGES.map((l) => (
            <option key={l} value={l}>
              {l}
            </option>
          ))}
        </select>
        <textarea
          value={instruction}
          onChange={(e) => setInstruction(e.target.value)}
          placeholder="Narration instruction…"
          rows={2}
          className={`md:col-span-3 ${inputCls}`}
        />
      </div>

      <div className="space-y-2">
        {profilesQ.isLoading && <p className="text-sm text-slate-500">Loading…</p>}
        {profiles.map((p) => (
          <div
            key={p.profile_id}
            className="flex items-start justify-between gap-4 bg-zinc-900/60 border border-zinc-800 rounded-lg px-4 py-3"
          >
            {editingId === p.profile_id ? (
              <div className="flex-1 grid grid-cols-1 md:grid-cols-3 gap-2 items-end">
                <input
                  aria-label="Edit name"
                  value={editName}
                  onChange={(e) => setEditName(e.target.value)}
                  className={inputCls}
                />
                <TagAutocompleteInput
                  ariaLabel="Edit trigger tags"
                  value={editTags}
                  onChange={setEditTags}
                  className={inputCls}
                />
                <div className="flex gap-2">
                  <button
                    onClick={() => updateM.mutate(p.profile_id)}
                    disabled={
                      !editName.trim() || !editInstruction.trim() || updateM.isPending
                    }
                    className="px-3 py-2 rounded-lg bg-purple-600 hover:bg-purple-500 disabled:opacity-40 text-sm text-white"
                  >
                    Save
                  </button>
                  <button
                    onClick={() => setEditingId(null)}
                    className="px-3 py-2 rounded-lg text-sm text-slate-400 hover:text-slate-200"
                  >
                    Cancel
                  </button>
                </div>
                <select
                  aria-label="Edit category"
                  value={editCategory}
                  onChange={(e) => setEditCategory(e.target.value)}
                  className={inputCls}
                >
                  {CATEGORIES.map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                </select>
                <select
                  aria-label="Edit language"
                  value={editLanguage}
                  onChange={(e) => setEditLanguage(e.target.value)}
                  className={inputCls}
                >
                  {LANGUAGES.map((l) => (
                    <option key={l} value={l}>
                      {l}
                    </option>
                  ))}
                </select>
                <textarea
                  aria-label="Edit instruction"
                  value={editInstruction}
                  onChange={(e) => setEditInstruction(e.target.value)}
                  rows={2}
                  className={`md:col-span-3 ${inputCls}`}
                />
              </div>
            ) : (
              <>
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-slate-100">{p.name}</span>
                    {p.is_builtin && (
                      <span className="text-[10px] uppercase px-1.5 py-0.5 rounded bg-cyan-500/10 text-cyan-300 border border-cyan-500/30">
                        builtin
                      </span>
                    )}
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-white/5 text-slate-500">
                      {p.category} · {p.language}
                    </span>
                  </div>
                  <p className="text-xs text-slate-400 mt-1">{p.instruction}</p>
                  <div className="flex gap-1 mt-1 flex-wrap">
                    {p.trigger_tags.map((t) => (
                      <span
                        key={t}
                        className="text-[10px] px-1.5 py-0.5 rounded bg-white/5 text-slate-400"
                      >
                        {t}
                      </span>
                    ))}
                  </div>
                </div>
                {!p.is_builtin && (
                  <div className="flex items-center gap-3 flex-shrink-0">
                    <button
                      onClick={() => startEdit(p)}
                      className="text-xs text-slate-400 hover:text-slate-200"
                    >
                      Edit
                    </button>
                    <button
                      onClick={() => deleteM.mutate(p.profile_id)}
                      className="text-xs text-red-400 hover:text-red-300"
                    >
                      Delete
                    </button>
                  </div>
                )}
              </>
            )}
          </div>
        ))}
      </div>

      <div>
        <h3 className="text-sm font-bold text-slate-200">Libraries</h3>
        <div className="mt-2 space-y-1">
          {libraries.map((l) => (
            <div
              key={l.library_id}
              className="flex items-center justify-between bg-zinc-900/40 border border-zinc-800 rounded-lg px-4 py-2"
            >
              <span className="text-sm text-slate-300">
                {l.name}
                {l.is_default && (
                  <span className="ml-2 text-[10px] uppercase text-emerald-400">default</span>
                )}
              </span>
              <span className="text-xs text-slate-500">{l.tone_profile_ids.length} profiles</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
