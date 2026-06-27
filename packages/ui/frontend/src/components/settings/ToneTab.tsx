"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toneApi } from "@/lib/api";

/**
 * Tone Profiles tab (CF-7). Reusable narration instructions matched by
 * trigger tags. Extracted from app/settings/page.tsx so the page stays
 * a thin tab orchestrator.
 */
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

  const createM = useMutation({
    mutationFn: () =>
      toneApi.createProfile({
        name,
        description: name,
        instruction,
        trigger_tags: tags
          .split(",")
          .map((t) => t.trim())
          .filter(Boolean),
        category: "custom",
        language: "en",
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["tone", "profiles"] });
      setName("");
      setInstruction("");
      setTags("");
    },
  });

  const deleteM = useMutation({
    mutationFn: (id: string) => toneApi.deleteProfile(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["tone", "profiles"] }),
  });

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
          className="bg-zinc-900 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-slate-200"
        />
        <input
          value={tags}
          onChange={(e) => setTags(e.target.value)}
          placeholder="Trigger tags (comma separated)"
          className="bg-zinc-900 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-slate-200"
        />
        <button
          onClick={() => createM.mutate()}
          disabled={!name.trim() || !instruction.trim() || createM.isPending}
          className="px-3 py-2 rounded-lg bg-purple-600 hover:bg-purple-500 disabled:opacity-40 text-sm text-white"
        >
          Add profile
        </button>
        <textarea
          value={instruction}
          onChange={(e) => setInstruction(e.target.value)}
          placeholder="Narration instruction…"
          rows={2}
          className="md:col-span-3 bg-zinc-900 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-slate-200"
        />
      </div>

      <div className="space-y-2">
        {profilesQ.isLoading && <p className="text-sm text-slate-500">Loading…</p>}
        {profiles.map((p) => (
          <div
            key={p.profile_id}
            className="flex items-start justify-between gap-4 bg-zinc-900/60 border border-zinc-800 rounded-lg px-4 py-3"
          >
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium text-slate-100">{p.name}</span>
                {p.is_builtin && (
                  <span className="text-[10px] uppercase px-1.5 py-0.5 rounded bg-cyan-500/10 text-cyan-300 border border-cyan-500/30">
                    builtin
                  </span>
                )}
              </div>
              <p className="text-xs text-slate-400 mt-1">{p.instruction}</p>
              <div className="flex gap-1 mt-1 flex-wrap">
                {p.trigger_tags.map((t) => (
                  <span key={t} className="text-[10px] px-1.5 py-0.5 rounded bg-white/5 text-slate-400">
                    {t}
                  </span>
                ))}
              </div>
            </div>
            {!p.is_builtin && (
              <button
                onClick={() => deleteM.mutate(p.profile_id)}
                className="text-xs text-red-400 hover:text-red-300 flex-shrink-0"
              >
                Delete
              </button>
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
