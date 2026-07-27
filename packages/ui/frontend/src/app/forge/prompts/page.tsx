"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2, MessageSquareText, Plus, Save, Trash2, X, ArrowUp, ArrowDown, History, RotateCcw } from "lucide-react";
import { promptCollectionsApi } from "@/lib/api";
import { FORGE_KEYS } from "@/lib/query-keys";
import { useWorldContext } from "@/lib/world-context";
import type { PromptCollection, PromptEntry } from "@/lib/types";
import { cn } from "@/lib/utils";

// ─── Forge Prompts (curated Session Zero / char-creation question sets) ──
// Author the prompt_collections the preplay flow consumes as authored
// questions (resolve_authored_session_zero_questions → SessionZeroLoop).

const CATEGORIES = ["session_zero", "character_creation"] as const;
const QUESTION_CATEGORIES = [
  "name",
  "origin",
  "bond",
  "fear",
  "motivation",
  "conflict",
  "secret",
  "loss",
  "appearance",
  "skill",
  "faith",
  "relationship",
  "custom",
];

type DraftEntry = Omit<PromptEntry, "entry_id"> & { entry_id?: string };

function emptyEntry(order: number): DraftEntry {
  return {
    order,
    category: "custom",
    question_text: "",
    answer_options: [],
    guidance: null,
    is_final: false,
  };
}

// ═══════════════════════════════════════════════════════════════
//  Entry row (editable)
// ═══════════════════════════════════════════════════════════════

function EntryRow({
  entry,
  index,
  total,
  onChange,
  onRemove,
  onMove,
}: {
  entry: DraftEntry;
  index: number;
  total: number;
  onChange: (index: number, entry: DraftEntry) => void;
  onRemove: (index: number) => void;
  onMove: (index: number, dir: -1 | 1) => void;
}) {
  return (
    <div className="flex flex-col gap-1.5 p-2.5 rounded-lg border border-white/5 bg-white/[0.02] group">
      <div className="flex items-center gap-2">
        <span className="text-[10px] text-slate-600 w-5 text-center flex-shrink-0">{index + 1}</span>
        <select
          value={entry.category}
          onChange={(e) => onChange(index, { ...entry, category: e.target.value })}
          className="input-cyber py-0.5 text-[10px] w-32 flex-shrink-0"
        >
          {QUESTION_CATEGORIES.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
        <label className="flex items-center gap-1 text-[10px] text-slate-500 ml-auto flex-shrink-0">
          <input
            type="checkbox"
            checked={entry.is_final}
            onChange={(e) => onChange(index, { ...entry, is_final: e.target.checked })}
          />
          final
        </label>
        <div className="flex items-center gap-0.5 flex-shrink-0">
          <button
            onClick={() => onMove(index, -1)}
            disabled={index === 0}
            className="text-slate-700 hover:text-cyan-400 disabled:opacity-20 transition-colors"
            title="Move up"
          >
            <ArrowUp className="w-3 h-3" />
          </button>
          <button
            onClick={() => onMove(index, 1)}
            disabled={index === total - 1}
            className="text-slate-700 hover:text-cyan-400 disabled:opacity-20 transition-colors"
            title="Move down"
          >
            <ArrowDown className="w-3 h-3" />
          </button>
          <button
            onClick={() => onRemove(index)}
            className="text-slate-700 hover:text-red-400 transition-colors"
            title="Remove"
          >
            <X className="w-3 h-3" />
          </button>
        </div>
      </div>
      <textarea
        value={entry.question_text}
        onChange={(e) => onChange(index, { ...entry, question_text: e.target.value })}
        className="input-cyber py-1 text-xs w-full resize-y min-h-[2rem]"
        placeholder="The in-fiction question the GM asks..."
        rows={2}
      />
      <input
        value={entry.answer_options.join(" | ")}
        onChange={(e) =>
          onChange(index, {
            ...entry,
            answer_options: e.target.value
              .split("|")
              .map((s) => s.trim())
              .filter(Boolean),
          })
        }
        className="input-cyber py-0.5 text-[11px] w-full"
        placeholder="Optional answer choices, separated by |"
      />
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
//  Editor (create / edit)
// ═══════════════════════════════════════════════════════════════

function CollectionEditor({
  collection,
  onClose,
}: {
  collection: PromptCollection | null;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const { universeId } = useWorldContext();
  const [name, setName] = useState(collection?.name ?? "");
  const [description, setDescription] = useState(collection?.description ?? "");
  const [category, setCategory] = useState(collection?.category ?? "session_zero");
  const [tags, setTags] = useState((collection?.tags ?? []).join(", "));
  const [entries, setEntries] = useState<DraftEntry[]>(
    collection?.entries.map((e) => ({ ...e })) ?? [emptyEntry(0)],
  );
  const [error, setError] = useState<string | null>(null);

  const isEdit = Boolean(collection);

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["forge-prompt-collections"] });

  const payloadEntries = () =>
    entries
      .filter((e) => e.question_text.trim())
      .map((e, i) => ({
        order: i,
        category: e.category,
        question_text: e.question_text.trim(),
        answer_options: e.answer_options,
        guidance: e.guidance,
        is_final: e.is_final,
      }));

  const saveMutation = useMutation({
    mutationFn: () => {
      const tagList = tags.split(",").map((t) => t.trim()).filter(Boolean);
      if (isEdit && collection) {
        return promptCollectionsApi.update(collection.collection_id, {
          name,
          description: description || null,
          category,
          tags: tagList,
          entries: payloadEntries(),
        });
      }
      return promptCollectionsApi.create({
        name,
        description: description || undefined,
        category,
        universe_id: universeId ?? undefined,
        tags: tagList,
        entries: payloadEntries(),
      });
    },
    onSuccess: () => {
      invalidate();
      onClose();
    },
    onError: (e: unknown) => setError(e instanceof Error ? e.message : "Save failed"),
  });

  const updateEntry = (index: number, entry: DraftEntry) =>
    setEntries((prev) => prev.map((e, i) => (i === index ? entry : e)));
  const removeEntry = (index: number) => setEntries((prev) => prev.filter((_, i) => i !== index));
  const moveEntry = (index: number, dir: -1 | 1) =>
    setEntries((prev) => {
      const next = [...prev];
      const target = index + dir;
      if (target < 0 || target >= next.length) return prev;
      [next[index], next[target]] = [next[target], next[index]];
      return next;
    });

  // ── Versioning (existing collections only) ──
  const versionsQuery = useQuery({
    queryKey: collection ? FORGE_KEYS.promptCollection(collection.collection_id) : ["forge-prompt-collection", "none"],
    queryFn: () => promptCollectionsApi.listVersions(collection!.collection_id),
    enabled: isEdit && Boolean(collection),
  });

  const publishMutation = useMutation({
    mutationFn: () => promptCollectionsApi.publish(collection!.collection_id),
    onSuccess: () => versionsQuery.refetch(),
    onError: (e: unknown) => setError(e instanceof Error ? e.message : "Publish failed"),
  });

  const restoreMutation = useMutation({
    mutationFn: (versionId: string) => promptCollectionsApi.restore(versionId),
    onSuccess: (restored) => {
      invalidate();
      // Reflect the restored content in the open editor.
      setName(restored.name);
      setDescription(restored.description ?? "");
      setCategory(restored.category);
      setTags(restored.tags.join(", "));
      setEntries(restored.entries.map((e) => ({ ...e })));
    },
    onError: (e: unknown) => setError(e instanceof Error ? e.message : "Restore failed"),
  });

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <div className="flex items-center gap-2 px-4 py-2 border-b border-white/5 flex-shrink-0">
        <h2 className="text-sm text-slate-200 font-medium">
          {isEdit ? "Edit collection" : "New collection"}
        </h2>
        <button onClick={onClose} className="ml-auto text-slate-500 hover:text-slate-300">
          <X className="w-4 h-4" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        <div className="grid grid-cols-2 gap-3">
          <label className="flex flex-col gap-1 text-[11px] text-slate-500">
            Name
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="input-cyber py-1 text-xs"
              placeholder="e.g. V5 Session Zero"
            />
          </label>
          <label className="flex flex-col gap-1 text-[11px] text-slate-500">
            Category
            <select
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              className="input-cyber py-1 text-xs"
            >
              {CATEGORIES.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </label>
        </div>
        <label className="flex flex-col gap-1 text-[11px] text-slate-500">
          Description
          <input
            value={description ?? ""}
            onChange={(e) => setDescription(e.target.value)}
            className="input-cyber py-1 text-xs"
            placeholder="What this interview is for..."
          />
        </label>
        <label className="flex flex-col gap-1 text-[11px] text-slate-500">
          Tags (comma-separated)
          <input
            value={tags}
            onChange={(e) => setTags(e.target.value)}
            className="input-cyber py-1 text-xs"
            placeholder="gothic, vampire"
          />
        </label>

        <div className="flex items-center justify-between pt-2">
          <span className="text-[11px] text-slate-400 uppercase tracking-wide">Questions</span>
          <button
            onClick={() => setEntries((prev) => [...prev, emptyEntry(prev.length)])}
            className="flex items-center gap-1 text-[11px] text-cyan-300 hover:text-cyan-200"
          >
            <Plus className="w-3 h-3" /> Add question
          </button>
        </div>
        <div className="space-y-2">
          {entries.map((entry, index) => (
            <EntryRow
              key={entry.entry_id ?? index}
              entry={entry}
              index={index}
              total={entries.length}
              onChange={updateEntry}
              onRemove={removeEntry}
              onMove={moveEntry}
            />
          ))}
          {entries.length === 0 && (
            <p className="text-[11px] text-slate-600 italic py-4 text-center">
              No questions yet — add one above.
            </p>
          )}
        </div>

        {isEdit && (
          <div className="pt-3 mt-1 border-t border-white/5">
            <div className="flex items-center justify-between">
              <span className="flex items-center gap-1.5 text-[11px] text-slate-400 uppercase tracking-wide">
                <History className="w-3 h-3" /> Versions
              </span>
              <button
                onClick={() => publishMutation.mutate()}
                disabled={publishMutation.isPending}
                className="flex items-center gap-1 text-[11px] text-cyan-300 hover:text-cyan-200 disabled:opacity-50"
              >
                {publishMutation.isPending ? <Loader2 className="w-3 h-3 animate-spin" /> : <Save className="w-3 h-3" />}
                Publish snapshot
              </button>
            </div>
            <div className="mt-2 space-y-1">
              {(versionsQuery.data?.versions ?? []).map((v) => (
                <div
                  key={v.version_id}
                  className="flex items-center gap-2 text-[11px] text-slate-400 py-1 px-2 rounded bg-white/[0.02]"
                >
                  <span className="text-slate-300 font-mono">{v.version}</span>
                  <span className="text-slate-600 truncate flex-1">{v.note ?? "—"}</span>
                  <button
                    onClick={() => {
                      if (confirm(`Restore ${v.version}? This overwrites the current draft.`))
                        restoreMutation.mutate(v.version_id);
                    }}
                    className="flex items-center gap-1 text-slate-500 hover:text-emerald-300"
                    title="Restore this version"
                  >
                    <RotateCcw className="w-3 h-3" /> Restore
                  </button>
                </div>
              ))}
              {versionsQuery.data && versionsQuery.data.total === 0 && (
                <p className="text-[10px] text-slate-600 italic">No published versions yet.</p>
              )}
            </div>
          </div>
        )}
      </div>

      <div className="flex items-center gap-2 px-4 py-2 border-t border-white/5 flex-shrink-0">
        {error && <span className="text-[11px] text-red-400">{error}</span>}
        <button
          onClick={() => {
            setError(null);
            if (!name.trim()) {
              setError("Name is required");
              return;
            }
            saveMutation.mutate();
          }}
          disabled={saveMutation.isPending}
          className="ml-auto flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg bg-emerald-500/15 text-emerald-300 border border-emerald-500/30 hover:bg-emerald-500/25 disabled:opacity-50"
        >
          {saveMutation.isPending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
          {isEdit ? "Save changes" : "Create"}
        </button>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
//  Page (list + editor)
// ═══════════════════════════════════════════════════════════════

export default function ForgePromptsPage() {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState<PromptCollection | null | "new">(null);

  const { data, isLoading } = useQuery({
    queryKey: FORGE_KEYS.promptCollections(),
    queryFn: () => promptCollectionsApi.list({ limit: 200 }),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => promptCollectionsApi.delete(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["forge-prompt-collections"] }),
  });

  const collections = data?.collections ?? [];

  if (editing !== null) {
    return (
      <CollectionEditor
        collection={editing === "new" ? null : editing}
        onClose={() => setEditing(null)}
      />
    );
  }

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <div className="flex items-center gap-2 px-4 py-2 border-b border-white/5 flex-shrink-0">
        <MessageSquareText className="w-4 h-4 text-emerald-300" />
        <h1 className="text-sm text-slate-200 font-medium">Prompt Collections</h1>
        <span className="text-[10px] text-slate-600">
          Curated Session Zero / character-creation question sets
        </span>
        <button
          onClick={() => setEditing("new")}
          className="ml-auto flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg bg-emerald-500/15 text-emerald-300 border border-emerald-500/30 hover:bg-emerald-500/25"
        >
          <Plus className="w-3.5 h-3.5" /> New collection
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-4">
        {isLoading ? (
          <div className="flex items-center justify-center py-12 text-slate-500">
            <Loader2 className="w-5 h-5 animate-spin" />
          </div>
        ) : collections.length === 0 ? (
          <p className="text-xs text-slate-600 italic py-12 text-center">
            No prompt collections yet. Create one to author a Session Zero interview.
          </p>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {collections.map((c) => (
              <div
                key={c.collection_id}
                className={cn(
                  "flex flex-col gap-2 p-3 rounded-lg border border-white/5 bg-white/[0.02]",
                  "hover:border-emerald-500/20 transition-colors",
                )}
              >
                <div className="flex items-start gap-2">
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-slate-200 truncate">{c.name}</p>
                    <p className="text-[10px] text-slate-500">
                      {c.category} · {c.entries.length} question{c.entries.length === 1 ? "" : "s"}
                    </p>
                  </div>
                  {c.is_builtin && (
                    <span className="text-[9px] text-amber-300/70 border border-amber-500/20 rounded px-1 py-0.5">
                      builtin
                    </span>
                  )}
                </div>
                {c.description && <p className="text-[11px] text-slate-500 line-clamp-2">{c.description}</p>}
                <div className="flex items-center gap-2 mt-auto pt-1">
                  <button
                    onClick={() => setEditing(c)}
                    className="text-[11px] text-cyan-300 hover:text-cyan-200"
                  >
                    Edit
                  </button>
                  <button
                    onClick={() => {
                      if (confirm(`Delete "${c.name}"?`)) deleteMutation.mutate(c.collection_id);
                    }}
                    className="text-[11px] text-slate-600 hover:text-red-400 ml-auto flex items-center gap-1"
                  >
                    <Trash2 className="w-3 h-3" /> Delete
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
