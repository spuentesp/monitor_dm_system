"use client";

import { useCallback, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  BookOpen,
  ChevronDown,
  ChevronUp,
  Download,
  Edit2,
  Loader2,
  Tag,
  Trash2,
  Plus,
  Upload,
  X,
  TrendingUp,
  Filter,
} from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { cn } from "@/lib/utils";
import { graphApi, lorebookApi } from "@/lib/api";
import type { LorebookEntry, LorebookEntryCreate, LorebookIngestRequest } from "@/lib/types";
import { chunkLorebookEntries, lorebookChunksForText } from "./lorebookChunking";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface LorebookEditorProps {
  /** Character scope. When omitted, `universeId` mode shows a scope picker. */
  characterId?: string;
  /**
   * Universe scope (F3-4.4): renders a character selector for the universe
   * plus a "Universe-wide" pseudo-character using the `universe:<id>`
   * convention from the backend lorebook schema.
   */
  universeId?: string;
  onClose?: () => void;
}

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type SortField = "priority" | "trigger_count" | "created_at";

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function SortHeader({
  label,
  field,
  current,
  ascending,
  onSort,
}: {
  label: string;
  field: SortField;
  current: SortField;
  ascending: boolean;
  onSort: (f: SortField, asc: boolean) => void;
}) {
  const active = current === field;
  return (
    <button
      onClick={() => onSort(field, active && !ascending ? false : true)}
      className={cn(
        "flex items-center gap-1 text-xs font-medium uppercase tracking-wider",
        active ? "text-blue-400" : "text-gray-500 hover:text-gray-300",
      )}
    >
      {label}
      {active && (ascending ? <ChevronUp size={12} /> : <ChevronDown size={12} />)}
    </button>
  );
}

function LorebookRow({
  entry,
  onEdit,
  onDelete,
}: {
  entry: LorebookEntry;
  onEdit: (e: LorebookEntry) => void;
  onDelete: (id: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="border-b border-gray-800">
      {/* Row */}
      <div className="grid grid-cols-[1fr_auto_auto_auto] gap-4 items-center px-4 py-3 hover:bg-gray-800/40">
        {/* Keywords + preview */}
        <div className="min-w-0">
          <div className="flex flex-wrap gap-1 mb-1">
            {entry.keywords.slice(0, 4).map((kw) => (
              <span
                key={kw}
                className="inline-flex items-center px-2 py-0.5 rounded bg-blue-900/50 text-blue-300 text-xs"
              >
                {kw}
              </span>
            ))}
            {entry.keywords.length > 4 && (
              <span className="text-xs text-gray-500">+{entry.keywords.length - 4}</span>
            )}
          </div>
          <p className="text-sm text-gray-400 truncate">{entry.content}</p>
        </div>

        {/* Stats */}
        <div className="flex flex-col items-end gap-1">
          {entry.trigger_count > 0 && (
            <span className="flex items-center gap-1 text-xs text-green-400">
              <TrendingUp size={11} />
              {entry.trigger_count}
            </span>
          )}
          <span
            className={cn(
              "text-xs px-2 py-0.5 rounded",
              entry.priority >= 80
                ? "bg-red-900/50 text-red-300"
                : entry.priority >= 50
                  ? "bg-yellow-900/50 text-yellow-300"
                  : "bg-gray-700 text-gray-400",
            )}
          >
            P{entry.priority}
          </span>
        </div>

        {/* Tags */}
        <div className="flex flex-wrap gap-1 max-w-[120px]">
          {entry.tags.slice(0, 2).map((tag) => (
            <span
              key={tag}
              className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded bg-purple-900/40 text-purple-300"
            >
              <Tag size={9} />
              {tag}
            </span>
          ))}
        </div>

        {/* Actions */}
        <div className="flex items-center gap-1">
          <button
            onClick={() => setExpanded(!expanded)}
            className="p-1.5 rounded hover:bg-gray-700 text-gray-400"
            title="Expand"
          >
            <ChevronDown size={14} />
          </button>
          <button
            onClick={() => onEdit(entry)}
            className="p-1.5 rounded hover:bg-gray-700 text-gray-400"
            title="Edit"
          >
            <Edit2 size={14} />
          </button>
          <button
            onClick={() => onDelete(entry.id)}
            className="p-1.5 rounded hover:bg-red-900/40 text-gray-400 hover:text-red-400"
            title="Delete"
          >
            <Trash2 size={14} />
          </button>
        </div>
      </div>

      {/* Expanded detail */}
      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ height: 0 }}
            animate={{ height: "auto" }}
            exit={{ height: 0 }}
            className="px-4 pb-3 overflow-hidden"
          >
            <div className="bg-gray-900/50 rounded p-3 text-sm text-gray-300">
              <p className="mb-2">{entry.content}</p>
              {entry.last_triggered && (
                <p className="text-xs text-gray-600">
                  Last triggered: {new Date(entry.last_triggered).toLocaleDateString()}
                </p>
              )}
              {entry.scene_filter && (
                <p className="text-xs text-gray-600">Scene filter: {entry.scene_filter}</p>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

// ---------------------------------------------------------------------------
// LorebookEditor
// ---------------------------------------------------------------------------

export function LorebookEditor({ characterId, universeId, onClose }: LorebookEditorProps) {
  const qc = useQueryClient();

  // Universe mode (F3-4.4): pick a character of the universe, or the
  // "universe-wide" pseudo-character (`universe:<id>` backend convention).
  const universeWideId = universeId ? `universe:${universeId}` : null;
  const [selectedScopeId, setSelectedScopeId] = useState<string | null>(
    characterId ?? universeWideId,
  );
  const effectiveCharacterId = characterId ?? selectedScopeId ?? "";

  const charactersQ = useQuery({
    queryKey: ["universeCharacters", universeId],
    queryFn: () =>
      graphApi.getWorldGraph({ universe_id: universeId, entity_types: ["character"] }),
    enabled: !!universeId && !characterId,
    staleTime: 30_000,
  });
  const universeCharacters = (charactersQ.data?.nodes ?? []).map((n) => ({
    id: n.id,
    label: n.data.label,
  }));

  const [sortField, setSortField] = useState<SortField>("trigger_count");
  const [sortAsc, setSortAsc] = useState(false);
  const [editingEntry, setEditingEntry] = useState<LorebookEntry | null>(null);
  const [isCreating, setIsCreating] = useState(false);
  const [newKeywords, setNewKeywords] = useState("");
  const [newSecondaryKeywords, setNewSecondaryKeywords] = useState("");
  const [newComment, setNewComment] = useState("");
  const [newContent, setNewContent] = useState("");
  const [newPriority, setNewPriority] = useState(50);
  const [newOrder, setNewOrder] = useState(100);
  const [newPosition, setNewPosition] = useState(1);
  const [newDepth, setNewDepth] = useState(4);
  const [newConstant, setNewConstant] = useState(false);
  const [newSelective, setNewSelective] = useState(false);
  const [newSelectiveLogic, setNewSelectiveLogic] = useState(0);
  const [newProbability, setNewProbability] = useState(100);
  const [newUseProbability, setNewUseProbability] = useState(true);
  const [newCaseSensitive, setNewCaseSensitive] = useState<boolean | null>(null);
  const [newMatchWholeWords, setNewMatchWholeWords] = useState<boolean | null>(null);
  const [newTags, setNewTags] = useState("");
  const [newGroup, setNewGroup] = useState("");
  const [newGroupOverride, setNewGroupOverride] = useState(false);
  const [newSticky, setNewSticky] = useState(0);
  const [newCooldown, setNewCooldown] = useState(0);
  const [newDelay, setNewDelay] = useState(0);
  const [newExcludeRecursion, setNewExcludeRecursion] = useState(false);
  const [newPreventRecursion, setNewPreventRecursion] = useState(false);
  const [newVectorized, setNewVectorized] = useState(false);
  const [showAdvanced, setShowAdvanced] = useState(false);

  // Ingest state (M3-G.2)
  const [isIngesting, setIsIngesting] = useState(false);
  const [ingestProgress, setIngestProgress] = useState({ done: 0, total: 0 });
  const [ingestSource, setIngestSource] = useState("");
  const [ingestContent, setIngestContent] = useState("");
  // Stored as strings so an empty input shows an empty field instead of
  // silently snapping back to the default. Parsed on submit, with safe
  // fallback if the user submits with an empty / invalid value.
  const [ingestChunkSize, setIngestChunkSize] = useState("1000");
  const [ingestAutoKeywords, setIngestAutoKeywords] = useState(true);
  const [ingestPriority, setIngestPriority] = useState("50");
  const [ingestTags, setIngestTags] = useState("");

  // Fetch lorebook entries
  const { data: entries = [], isLoading } = useQuery({
    queryKey: ["lorebook", effectiveCharacterId],
    queryFn: () => lorebookApi.list(effectiveCharacterId) as Promise<LorebookEntry[]>,
    enabled: !!effectiveCharacterId,
  });

  // Fetch stats
  const { data: stats } = useQuery({
    queryKey: ["lorebook-stats", effectiveCharacterId],
    queryFn: () => lorebookApi.stats(effectiveCharacterId),
    enabled: !!effectiveCharacterId,
  });

  const createMutation = useMutation({
    mutationFn: (data: LorebookEntryCreate) => lorebookApi.create(effectiveCharacterId, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["lorebook", effectiveCharacterId] });
      qc.invalidateQueries({ queryKey: ["lorebook-stats", effectiveCharacterId] });
      resetForm();
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, body }: { id: string; body: Partial<LorebookEntry> }) =>
      lorebookApi.update(id, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["lorebook", effectiveCharacterId] });
      setEditingEntry(null);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => lorebookApi.remove(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["lorebook", effectiveCharacterId] });
      qc.invalidateQueries({ queryKey: ["lorebook-stats", effectiveCharacterId] });
    },
  });

  // M3-G.2: Ingest document mutation
  //
  // Chunks the document locally and posts in BATCHES of ~20 chunks so a
  // large document (e.g. a 50-page book at chunk_size=200 → ~300 chunks)
  // doesn't blow the backend's default 30s request timeout on a single
  // bulkCreate POST. Batches are sequential so failures are localized —
  // a 500 on batch 7 still saves batches 1-6.
  const LOREBOOK_INGEST_BATCH = 20;
  const importMutation = useMutation({
    mutationFn: (file: File) => lorebookApi.import(effectiveCharacterId, file),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["lorebook", effectiveCharacterId] });
      qc.invalidateQueries({ queryKey: ["lorebook-stats", effectiveCharacterId] });
    },
  });

  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const ingestMutation = useMutation({
    mutationFn: async (data: LorebookIngestRequest) => {
      const chunks = lorebookChunksForText(data.content ?? "", data.chunk_size ?? 1000);
      const entries = chunks.map((chunk, idx) => ({
        keywords: data.auto_keywords
          ? Array.from(
              new Set(
                chunk
                  .split(/\W+/)
                  .filter((w) => w.length > 4)
                  .slice(0, 5)
                  .map((w) => w.toLowerCase()),
              ),
            )
          : [],
        content: chunk,
        priority: data.priority_hint ?? 50,
        tags: [...(data.tags ?? []), data.source ? `src:${data.source}` : `chunk:${idx + 1}`],
      }));
      setIngestProgress({ done: 0, total: entries.length });
      // Batch POSTs so a 300-chunk document doesn't blow the backend's
      // 30s request timeout on a single bulkCreate call.
      const created: unknown[] = [];
      for (const batch of chunkLorebookEntries(entries, LOREBOOK_INGEST_BATCH)) {
        const result = await lorebookApi.bulkCreate(effectiveCharacterId, batch);
        created.push(...result);
        setIngestProgress({ done: Math.min(entries.length, created.length), total: entries.length });
      }
      return created;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["lorebook", effectiveCharacterId] });
      qc.invalidateQueries({ queryKey: ["lorebook-stats", effectiveCharacterId] });
      setIsIngesting(false);
      setIngestSource("");
      setIngestContent("");
      setIngestChunkSize("1000");
      setIngestProgress({ done: 0, total: 0 });
      setIngestAutoKeywords(true);
      setIngestPriority("50");
      setIngestTags("");
    },
  });

  const resetForm = () => {
    setIsCreating(false);
    setEditingEntry(null);
    setNewKeywords("");
    setNewSecondaryKeywords("");
    setNewComment("");
    setNewContent("");
    setNewPriority(50);
    setNewOrder(100);
    setNewPosition(1);
    setNewDepth(4);
    setNewConstant(false);
    setNewSelective(false);
    setNewSelectiveLogic(0);
    setNewProbability(100);
    setNewUseProbability(true);
    setNewCaseSensitive(null);
    setNewMatchWholeWords(null);
    setNewTags("");
    setNewGroup("");
    setNewGroupOverride(false);
    setNewSticky(0);
    setNewCooldown(0);
    setNewDelay(0);
    setNewExcludeRecursion(false);
    setNewPreventRecursion(false);
    setNewVectorized(false);
    setShowAdvanced(false);
  };

  const buildPayload = (): LorebookEntryCreate => ({
    keywords: newKeywords.split(",").map((k) => k.trim().toLowerCase()).filter(Boolean),
    secondary_keywords: newSecondaryKeywords.split(",").map((k) => k.trim().toLowerCase()).filter(Boolean),
    comment: newComment.trim(),
    content: newContent.trim(),
    priority: newPriority,
    order: newOrder,
    position: newPosition,
    depth: newDepth,
    constant: newConstant,
    selective: newSelective,
    selective_logic: newSelectiveLogic,
    probability: newProbability,
    use_probability: newUseProbability,
    case_sensitive: newCaseSensitive,
    match_whole_words: newMatchWholeWords,
    tags: newTags.split(",").map((t) => t.trim()).filter(Boolean),
    group: newGroup.trim(),
    group_override: newGroupOverride,
    sticky: newSticky,
    cooldown: newCooldown,
    delay: newDelay,
    exclude_recursion: newExcludeRecursion,
    prevent_recursion: newPreventRecursion,
    vectorized: newVectorized,
  });

  const handleSort = (field: SortField, asc: boolean) => {
    setSortField(field);
    setSortAsc(asc);
  };

  const sorted = [...(entries as LorebookEntry[])].sort((a, b) => {
    const aVal = a[sortField] ?? 0;
    const bVal = b[sortField] ?? 0;
    if (sortAsc) return aVal > bVal ? 1 : -1;
    return aVal < bVal ? 1 : -1;
  });

  const handleSaveNew = () => {
    if (!newContent.trim()) return;
    createMutation.mutate(buildPayload());
  };

  const handleSaveEdit = () => {
    if (!editingEntry || !newContent.trim()) return;
    updateMutation.mutate({
      id: editingEntry.id,
      body: buildPayload(),
    });
  };

  return (
    <div className="flex flex-col h-full bg-gray-950">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-800">
        <div className="flex items-center gap-2">
          <BookOpen size={16} className="text-blue-400" />
          <span className="font-medium text-sm">Lorebook</span>
          {universeId && !characterId && (
            <select
              aria-label="Lorebook scope"
              value={effectiveCharacterId}
              onChange={(e) => setSelectedScopeId(e.target.value)}
              className="bg-gray-800 border border-gray-700 rounded px-2 py-1 text-xs text-gray-200"
            >
              {universeWideId && <option value={universeWideId}>Universe-wide</option>}
              {universeCharacters.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.label}
                </option>
              ))}
            </select>
          )}
          {stats && (
            <span className="text-xs text-gray-500">
              {stats.total_entries} entries · {stats.total_triggers} triggers
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <input
            ref={fileInputRef}
            type="file"
            accept=".json,application/json"
            className="hidden"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) importMutation.mutate(file);
              if (e.target) e.target.value = "";
            }}
          />
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={importMutation.isPending}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded bg-gray-700 hover:bg-gray-600 text-xs font-medium disabled:opacity-50"
          >
            {importMutation.isPending ? <Loader2 size={13} className="animate-spin" /> : <Upload size={13} />}
            Import ST
          </button>
          <button
            onClick={() => lorebookApi.export(effectiveCharacterId)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded bg-gray-700 hover:bg-gray-600 text-xs font-medium"
          >
            <Download size={13} />
            Export ST
          </button>
          <button
            onClick={() => setIsIngesting(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded bg-purple-600 hover:bg-purple-500 text-xs font-medium"
          >
            <BookOpen size={13} />
            Ingest Document
          </button>
          <button
            onClick={() => setIsCreating(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded bg-blue-600 hover:bg-blue-500 text-xs font-medium"
          >
            <Plus size={13} />
            Add Entry
          </button>
          {onClose && (
            <button onClick={onClose} aria-label="Close" className="p-1.5 rounded hover:bg-gray-800 text-gray-400">
              <X size={16} />
            </button>
          )}
        </div>
      </div>

      {/* Sort bar */}
      <div className="grid grid-cols-[1fr_auto_auto_auto] gap-4 px-4 py-2 border-b border-gray-800/50 bg-gray-900/30">
        <SortHeader label="Keywords" field="priority" current={sortField} ascending={sortAsc} onSort={handleSort} />
        <div className="flex items-center gap-1">
          <SortHeader label="Triggers" field="trigger_count" current={sortField} ascending={sortAsc} onSort={handleSort} />
        </div>
        <span className="text-xs text-gray-600">Tags</span>
        <span />
      </div>

      {/* List */}
      <div className="flex-1 overflow-y-auto">
        {isLoading ? (
          <div className="flex items-center justify-center py-8 text-gray-500">
            <Loader2 size={16} className="animate-spin mr-2" />
            Loading...
          </div>
        ) : sorted.length === 0 ? (
          <div className="flex flex-col items-center py-8 text-gray-500">
            <BookOpen size={24} className="mb-2 opacity-50" />
            <p className="text-sm">No lorebook entries yet</p>
            <p className="text-xs mt-1">Add entries or ingest a document to get started</p>
          </div>
        ) : (
          sorted.map((entry) => (
            <LorebookRow
              key={entry.id}
              entry={entry}
              onEdit={(e) => {
                setEditingEntry(e);
                setNewKeywords(e.keywords.join(", "));
                setNewSecondaryKeywords(e.secondary_keywords.join(", "));
                setNewComment(e.comment || "");
                setNewContent(e.content);
                setNewPriority(e.priority);
                setNewOrder(e.order);
                setNewPosition(e.position);
                setNewDepth(e.depth);
                setNewConstant(e.constant);
                setNewSelective(e.selective);
                setNewSelectiveLogic(e.selective_logic);
                setNewProbability(e.probability);
                setNewUseProbability(e.use_probability);
                setNewCaseSensitive(e.case_sensitive);
                setNewMatchWholeWords(e.match_whole_words);
                setNewTags(e.tags.join(", "));
                setNewGroup(e.group || "");
                setNewGroupOverride(e.group_override);
                setNewSticky(e.sticky);
                setNewCooldown(e.cooldown);
                setNewDelay(e.delay);
                setNewExcludeRecursion(e.exclude_recursion);
                setNewPreventRecursion(e.prevent_recursion);
                setNewVectorized(e.vectorized);
              }}
              onDelete={(id) => deleteMutation.mutate(id)}
            />
          ))
        )}
      </div>

      {/* Create/Edit panel */}
      <AnimatePresence>
        {(isCreating || editingEntry) && (
          <motion.div
            initial={{ height: 0 }}
            animate={{ height: "auto" }}
            exit={{ height: 0 }}
            className="border-t border-gray-800 overflow-hidden"
          >
            <div className="p-4 bg-gray-900/50 space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium">
                  {editingEntry ? "Edit Entry" : "New Entry"}
                </span>
                <button
                  onClick={resetForm}
                  className="text-xs text-gray-500 hover:text-gray-300"
                >
                  Cancel
                </button>
              </div>

              <div>
                <label className="text-xs text-gray-500 mb-1 block">Title / Comment</label>
                <input
                  type="text"
                  value={newComment}
                  onChange={(e) => setNewComment(e.target.value)}
                  placeholder="Dragon weaknesses"
                  className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm text-gray-200 placeholder-gray-600 focus:border-blue-500 focus:outline-none"
                />
              </div>

              <div>
                <label className="text-xs text-gray-500 mb-1 block">Keywords (comma-separated)</label>
                <input
                  type="text"
                  value={newKeywords}
                  onChange={(e) => setNewKeywords(e.target.value)}
                  placeholder="dragon, wyrm, hoard"
                  className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm text-gray-200 placeholder-gray-600 focus:border-blue-500 focus:outline-none"
                />
              </div>

              <div>
                <label className="text-xs text-gray-500 mb-1 block">Content</label>
                <textarea
                  value={newContent}
                  onChange={(e) => setNewContent(e.target.value)}
                  rows={3}
                  placeholder="Dragons are immune to fire. Their weakness is their underbelly."
                  className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm text-gray-200 placeholder-gray-600 focus:border-blue-500 focus:outline-none resize-none"
                />
              </div>

              <div className="grid grid-cols-4 gap-3">
                <div>
                  <label className="text-xs text-gray-500 mb-1 block">Priority</label>
                  <input
                    type="number"
                    min={0}
                    max={100}
                    value={newPriority}
                    onChange={(e) => setNewPriority(parseInt(e.target.value) || 0)}
                    className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm text-gray-200 focus:border-blue-500 focus:outline-none"
                  />
                </div>
                <div>
                  <label className="text-xs text-gray-500 mb-1 block">Order</label>
                  <input
                    type="number"
                    min={0}
                    max={1000}
                    value={newOrder}
                    onChange={(e) => setNewOrder(parseInt(e.target.value) || 0)}
                    className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm text-gray-200 focus:border-blue-500 focus:outline-none"
                  />
                </div>
                <div>
                  <label className="text-xs text-gray-500 mb-1 block">Position</label>
                  <select
                    value={newPosition}
                    onChange={(e) => setNewPosition(parseInt(e.target.value))}
                    className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm text-gray-200 focus:border-blue-500 focus:outline-none"
                  >
                    <option value={0}>Before char</option>
                    <option value={1}>After char</option>
                    <option value={2}>AN top</option>
                    <option value={3}>AN bottom</option>
                    <option value={4}>@Depth</option>
                  </select>
                </div>
                <div>
                  <label className="text-xs text-gray-500 mb-1 block">Depth</label>
                  <input
                    type="number"
                    min={0}
                    max={100}
                    value={newDepth}
                    onChange={(e) => setNewDepth(parseInt(e.target.value) || 0)}
                    disabled={newPosition !== 4}
                    className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm text-gray-200 focus:border-blue-500 focus:outline-none disabled:opacity-50"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs text-gray-500 mb-1 block">Tags (comma-separated)</label>
                  <input
                    type="text"
                    value={newTags}
                    onChange={(e) => setNewTags(e.target.value)}
                    placeholder="combat, castle"
                    className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm text-gray-200 placeholder-gray-600 focus:border-blue-500 focus:outline-none"
                  />
                </div>
                <div>
                  <label className="text-xs text-gray-500 mb-1 block">Group</label>
                  <input
                    type="text"
                    value={newGroup}
                    onChange={(e) => setNewGroup(e.target.value)}
                    placeholder="monsters"
                    className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm text-gray-200 placeholder-gray-600 focus:border-blue-500 focus:outline-none"
                  />
                </div>
              </div>

              <div className="flex flex-wrap gap-4">
                <label className="flex items-center gap-1.5 text-xs text-gray-400">
                  <input
                    type="checkbox"
                    checked={newConstant}
                    onChange={(e) => setNewConstant(e.target.checked)}
                    className="rounded"
                  />
                  Constant
                </label>
                <label className="flex items-center gap-1.5 text-xs text-gray-400">
                  <input
                    type="checkbox"
                    checked={newSelective}
                    onChange={(e) => setNewSelective(e.target.checked)}
                    className="rounded"
                  />
                  Selective
                </label>
                <label className="flex items-center gap-1.5 text-xs text-gray-400">
                  <input
                    type="checkbox"
                    checked={newGroupOverride}
                    onChange={(e) => setNewGroupOverride(e.target.checked)}
                    className="rounded"
                  />
                  Group override
                </label>
                <label className="flex items-center gap-1.5 text-xs text-gray-400">
                  <input
                    type="checkbox"
                    checked={newExcludeRecursion}
                    onChange={(e) => setNewExcludeRecursion(e.target.checked)}
                    className="rounded"
                  />
                  Exclude recursion
                </label>
                <label className="flex items-center gap-1.5 text-xs text-gray-400">
                  <input
                    type="checkbox"
                    checked={newPreventRecursion}
                    onChange={(e) => setNewPreventRecursion(e.target.checked)}
                    className="rounded"
                  />
                  Prevent recursion
                </label>
                <label className="flex items-center gap-1.5 text-xs text-gray-400">
                  <input
                    type="checkbox"
                    checked={newVectorized}
                    onChange={(e) => setNewVectorized(e.target.checked)}
                    className="rounded"
                  />
                  Vectorized
                </label>
              </div>

              <button
                type="button"
                onClick={() => setShowAdvanced(!showAdvanced)}
                className="text-xs text-gray-500 hover:text-gray-300 flex items-center gap-1"
              >
                {showAdvanced ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                Advanced ST options
              </button>

              {showAdvanced && (
                <div className="grid grid-cols-2 md:grid-cols-3 gap-3 border-t border-gray-800 pt-3">
                  <div>
                    <label className="text-xs text-gray-500 mb-1 block">Secondary keywords</label>
                    <input
                      type="text"
                      value={newSecondaryKeywords}
                      onChange={(e) => setNewSecondaryKeywords(e.target.value)}
                      placeholder="fire, flame"
                      className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm text-gray-200 placeholder-gray-600 focus:border-blue-500 focus:outline-none"
                    />
                  </div>
                  <div>
                    <label className="text-xs text-gray-500 mb-1 block">Selective logic</label>
                    <select
                      value={newSelectiveLogic}
                      onChange={(e) => setNewSelectiveLogic(parseInt(e.target.value))}
                      disabled={!newSelective}
                      className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm text-gray-200 focus:border-blue-500 focus:outline-none disabled:opacity-50"
                    >
                      <option value={0}>AND ANY</option>
                      <option value={1}>NOT ALL</option>
                      <option value={2}>NOT ANY</option>
                      <option value={3}>AND ALL</option>
                    </select>
                  </div>
                  <div>
                    <label className="text-xs text-gray-500 mb-1 block">Probability %</label>
                    <input
                      type="number"
                      min={0}
                      max={100}
                      value={newProbability}
                      onChange={(e) => setNewProbability(parseInt(e.target.value) || 0)}
                      disabled={!newUseProbability}
                      className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm text-gray-200 focus:border-blue-500 focus:outline-none disabled:opacity-50"
                    />
                  </div>
                  <div>
                    <label className="text-xs text-gray-500 mb-1 block">Sticky</label>
                    <input
                      type="number"
                      min={0}
                      max={100}
                      value={newSticky}
                      onChange={(e) => setNewSticky(parseInt(e.target.value) || 0)}
                      className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm text-gray-200 focus:border-blue-500 focus:outline-none"
                    />
                  </div>
                  <div>
                    <label className="text-xs text-gray-500 mb-1 block">Cooldown</label>
                    <input
                      type="number"
                      min={0}
                      max={100}
                      value={newCooldown}
                      onChange={(e) => setNewCooldown(parseInt(e.target.value) || 0)}
                      className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm text-gray-200 focus:border-blue-500 focus:outline-none"
                    />
                  </div>
                  <div>
                    <label className="text-xs text-gray-500 mb-1 block">Delay</label>
                    <input
                      type="number"
                      min={0}
                      max={100}
                      value={newDelay}
                      onChange={(e) => setNewDelay(parseInt(e.target.value) || 0)}
                      className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm text-gray-200 focus:border-blue-500 focus:outline-none"
                    />
                  </div>
                  <div className="flex items-center gap-4">
                    <label className="flex items-center gap-1.5 text-xs text-gray-400">
                      <input
                        type="checkbox"
                        checked={newUseProbability}
                        onChange={(e) => setNewUseProbability(e.target.checked)}
                        className="rounded"
                      />
                      Use probability
                    </label>
                  </div>
                  <div className="flex items-center gap-4">
                    <label className="flex items-center gap-1.5 text-xs text-gray-400">
                      <input
                        type="checkbox"
                        checked={newCaseSensitive ?? false}
                        onChange={(e) => setNewCaseSensitive(e.target.checked || null)}
                        className="rounded"
                      />
                      Case-sensitive
                    </label>
                  </div>
                  <div className="flex items-center gap-4">
                    <label className="flex items-center gap-1.5 text-xs text-gray-400">
                      <input
                        type="checkbox"
                        checked={newMatchWholeWords ?? false}
                        onChange={(e) => setNewMatchWholeWords(e.target.checked || null)}
                        className="rounded"
                      />
                      Whole words
                    </label>
                  </div>
                </div>
              )}

              <button
                onClick={editingEntry ? handleSaveEdit : handleSaveNew}
                disabled={createMutation.isPending || updateMutation.isPending}
                className="w-full flex items-center justify-center gap-2 px-4 py-2 rounded bg-blue-600 hover:bg-blue-500 text-sm font-medium disabled:opacity-50"
              >
                {createMutation.isPending || updateMutation.isPending ? (
                  <Loader2 size={14} className="animate-spin" />
                ) : (
                  <span>{editingEntry ? "Save Changes" : "Add Entry"}</span>
                )}
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* M3-G.2: Ingest Document panel */}
      <AnimatePresence>
        {isIngesting && (
          <motion.div
            initial={{ height: 0 }}
            animate={{ height: "auto" }}
            exit={{ height: 0 }}
            className="border-t border-purple-800 overflow-hidden"
          >
            <div className="p-4 bg-gray-900/50 space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium text-purple-300">Ingest Document</span>
                <button
                  onClick={() => setIsIngesting(false)}
                  className="text-xs text-gray-500 hover:text-gray-300"
                >
                  Cancel
                </button>
              </div>

              <div>
                <label className="text-xs text-gray-500 mb-1 block">Source name</label>
                <input
                  type="text"
                  value={ingestSource}
                  onChange={(e) => setIngestSource(e.target.value)}
                  placeholder="The Hobbit - Chapter 1"
                  className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm text-gray-200 placeholder-gray-600 focus:border-purple-500 focus:outline-none"
                />
              </div>

              <div>
                <label className="text-xs text-gray-500 mb-1 block">Content (paste book excerpt, lore doc, etc.)</label>
                <textarea
                  value={ingestContent}
                  onChange={(e) => setIngestContent(e.target.value)}
                  rows={6}
                  placeholder="In a hole in the ground there lived a hobbit..."
                  className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm text-gray-200 placeholder-gray-600 focus:border-purple-500 focus:outline-none resize-none"
                />
              </div>

              <div className="grid grid-cols-3 gap-3">
                <div>
                  <label className="text-xs text-gray-500 mb-1 block">Chunk size</label>
                  <input
                    type="number"
                    min={200}
                    max={5000}
                    value={ingestChunkSize}
                    onChange={(e) => setIngestChunkSize(e.target.value)}
                    className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm text-gray-200 focus:border-purple-500 focus:outline-none"
                  />
                </div>
                <div>
                  <label className="text-xs text-gray-500 mb-1 block">Priority hint</label>
                  <input
                    type="number"
                    min={0}
                    max={100}
                    value={ingestPriority}
                    onChange={(e) => setIngestPriority(e.target.value)}
                    className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm text-gray-200 focus:border-purple-500 focus:outline-none"
                  />
                </div>
                <div>
                  <label className="text-xs text-gray-500 mb-1 block">Tags</label>
                  <input
                    type="text"
                    value={ingestTags}
                    onChange={(e) => setIngestTags(e.target.value)}
                    placeholder="setting, lore"
                    className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm text-gray-200 placeholder-gray-600 focus:border-purple-500 focus:outline-none"
                  />
                </div>
              </div>

              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  id="ingest-auto-kw"
                  checked={ingestAutoKeywords}
                  onChange={(e) => setIngestAutoKeywords(e.target.checked)}
                  className="rounded"
                />
                <label htmlFor="ingest-auto-kw" className="text-xs text-gray-400">
                  Auto-generate keywords via AI
                </label>
              </div>

              <button
                onClick={() => {
                  if (!ingestSource.trim() || !ingestContent.trim()) return;
                  ingestMutation.mutate({
                    source: ingestSource.trim(),
                    content: ingestContent.trim(),
                    chunk_size: parseInt(ingestChunkSize, 10) || 1000,
                    auto_keywords: ingestAutoKeywords,
                    priority_hint: parseInt(ingestPriority, 10) || 50,
                    tags: ingestTags.split(",").map((t) => t.trim()).filter(Boolean),
                    character_id: effectiveCharacterId,
                  });
                }}
                disabled={ingestMutation.isPending || !ingestSource.trim() || !ingestContent.trim()}
                className="w-full flex items-center justify-center gap-2 px-4 py-2 rounded bg-purple-600 hover:bg-purple-500 text-sm font-medium disabled:opacity-50"
              >
                {ingestMutation.isPending ? (
                  <Loader2 size={14} className="animate-spin" />
                ) : (
                  <span>Ingest &amp; Create Entries</span>
                )}
              </button>

              {ingestMutation.isSuccess && (
                <p className="text-xs text-green-400">
                  Ingested {ingestMutation.data?.length ?? 0} entries from {ingestSource}
                </p>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}