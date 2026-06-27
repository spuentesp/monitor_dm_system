"use client";

import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import { AnimatePresence, motion } from "framer-motion";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Globe2,
  Layers,
  Loader2,
  MapPin,
  MemoryStick,
  Network,
  Plus,
  Search,
  Shield,
  Sparkles,
  User,
  Users,
  X,
} from "lucide-react";
import { entitiesApi, universesApi } from "@/lib/api";
import type {
  Multiverse,
  NPC,
  NPCDetail,
  Universe,
} from "@/lib/types";
import { cn, formatRelativeTime, truncate } from "@/lib/utils";
import { UniverseTree } from "@/components/worlds/UniverseTree";
import { useWorldContext } from "@/lib/world-context";
import { NPCCard } from "./NPCCard";
import { NPCDetailPanel } from "./NPCDetailPanel";
import { GraphTab } from "./GraphTab";

// ─── Tab definitions ───────────────────────────────────────────

const WORLD_TABS = [
  { id: "graph",     label: "World Graph",     icon: Network },
  { id: "hierarchy", label: "Tree & Stories",  icon: Globe2 },
  { id: "entities",  label: "Entities",        icon: Users },
] as const;

type WorldTab = (typeof WORLD_TABS)[number]["id"];

function CreateMultiverseForm({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated?: (mv: Multiverse) => void;
}) {
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [desc, setDesc] = useState("");

  const mut = useMutation({
    mutationFn: () => universesApi.createMultiverse({ name, description: desc || undefined }),
    onSuccess: (created) => {
      qc.invalidateQueries({ queryKey: ["multiverses"] });
      onCreated?.(created);
      onClose();
    },
  });

  return (
    <motion.div
      initial={{ opacity: 0, y: -6 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -6 }}
      className="glass-dark rounded-xl border border-purple-500/20 p-4 space-y-3"
    >
      <div className="flex items-center justify-between">
        <p className="text-xs font-semibold text-purple-300">New Multiverse</p>
        <button onClick={onClose} aria-label="Close" className="text-slate-600 hover:text-slate-300">
          <X className="w-3.5 h-3.5" />
        </button>
      </div>
      <input
        className="input-cyber w-full"
        placeholder="Name…"
        value={name}
        onChange={(e) => setName(e.target.value)}
        autoFocus
      />
      <input
        className="input-cyber w-full"
        placeholder="Description (optional)"
        value={desc}
        onChange={(e) => setDesc(e.target.value)}
      />
      <button
        onClick={() => mut.mutate()}
        disabled={!name.trim() || mut.isPending}
        className="btn-cyber w-full justify-center"
      >
        {mut.isPending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Plus className="w-3.5 h-3.5" />}
        Create
      </button>
    </motion.div>
  );
}

function CreateUniverseForm({
  multiverseId,
  onClose,
  onCreated,
}: {
  multiverseId: string;
  onClose: () => void;
  onCreated?: (universe: Universe) => void;
}) {
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [genre, setGenre] = useState("");
  const [desc, setDesc] = useState("");

  const mut = useMutation({
    mutationFn: () =>
      universesApi.createUniverse({
        name,
        multiverse_id: multiverseId,
        genre: genre || undefined,
        description: desc || undefined,
      }),
    onSuccess: (created) => {
      qc.invalidateQueries({ queryKey: ["universes"] });
      qc.invalidateQueries({ queryKey: ["multiverses"] });
      onCreated?.(created);
      onClose();
    },
  });

  const GENRES = ["Fantasy", "Sci-Fi", "Horror", "Cyberpunk", "Historical", "Modern", "Mystery", "Western", "Superhero"];

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.97 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0 }}
      className="glass rounded-2xl border border-cyan-500/20 p-5 space-y-4"
    >
      <div className="flex items-center justify-between">
        <p className="text-sm font-semibold text-slate-200">New Universe</p>
        <button onClick={onClose} className="text-slate-600 hover:text-slate-300">
          <X className="w-4 h-4" />
        </button>
      </div>

      <input
        className="input-cyber w-full"
        placeholder="Universe name…"
        value={name}
        onChange={(e) => setName(e.target.value)}
        autoFocus
      />

      <div>
        <p className="text-xs text-slate-600 mb-2">Genre</p>
        <div className="flex flex-wrap gap-2">
          {GENRES.map((g) => (
            <button
              key={g}
              onClick={() => setGenre(genre === g ? "" : g)}
              className={cn(
                "text-xs px-2.5 py-1 rounded-full border transition-all",
                genre === g
                  ? "bg-cyan-500/15 border-cyan-500/40 text-cyan-300"
                  : "border-white/10 text-slate-500 hover:border-white/20 hover:text-slate-300",
              )}
            >
              {g}
            </button>
          ))}
        </div>
      </div>

      <textarea
        className="input-cyber w-full resize-none"
        rows={2}
        placeholder="Short description (optional)"
        value={desc}
        onChange={(e) => setDesc(e.target.value)}
      />

      <button
        onClick={() => mut.mutate()}
        disabled={!name.trim() || mut.isPending}
        className="btn-cyber w-full justify-center"
      >
        {mut.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Globe2 className="w-4 h-4" />}
        Create Universe
      </button>
    </motion.div>
  );
}

function HierarchyTab() {
  const qc = useQueryClient();
  const searchParams = useSearchParams();
  const world = useWorldContext();
  // URL deep link wins; otherwise open the tree at the global world (T-077)
  const requestedUniverseId = searchParams.get("universe") ?? world.universeId;
  const [showMvForm, setShowMvForm] = useState(false);
  const [createUnderMvId, setCreateUnderMvId] = useState<string | null>(null);

  const { data: multiverses = [], isLoading: mvLoading } = useQuery({
    queryKey: ["multiverses"],
    queryFn: universesApi.listMultiverses,
  });

  const deleteUnivMut = useMutation({
    mutationFn: universesApi.deleteUniverse,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["universes"] });
      qc.invalidateQueries({ queryKey: ["multiverses"] });
    },
  });

  return (
    <div className="flex flex-col h-full">
      {/* Toolbar */}
      <div className="flex items-center gap-3 px-4 h-11 border-b border-white/5 glass-dark flex-shrink-0">
        {mvLoading ? (
          <span className="flex items-center gap-1.5 text-xs text-slate-600">
            <Loader2 className="w-3 h-3 animate-spin" /> loading…
          </span>
        ) : (
          <span className="text-xs text-slate-600">
            {multiverses.length} setting{multiverses.length !== 1 ? "s" : ""} · traverse settings →
            universes → stories → scenes
          </span>
        )}
        <div className="flex-1" />
        <div className="flex items-center gap-2">
          <select
            value={createUnderMvId ?? ""}
            onChange={(e) => setCreateUnderMvId(e.target.value || null)}
            className="input-cyber py-1 text-xs min-w-[150px]"
            title="Create a universe inside this setting"
          >
            <option value="">New universe in…</option>
            {multiverses.map((mv) => (
              <option key={mv.id} value={mv.id}>{mv.name}</option>
            ))}
          </select>
          <button onClick={() => setShowMvForm((v) => !v)} className="btn-cyber text-xs py-1.5">
            <Plus className="w-3.5 h-3.5" /> New Multiverse
          </button>
        </div>
      </div>

      {/* Create forms */}
      <AnimatePresence>
        {(showMvForm || createUnderMvId) && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.15 }}
            className="overflow-hidden border-b border-white/5 flex-shrink-0"
          >
            <div className="px-4 py-3 max-w-lg">
              {showMvForm ? (
                <CreateMultiverseForm
                  onClose={() => setShowMvForm(false)}
                  onCreated={(mv) => {
                    setShowMvForm(false);
                    setCreateUnderMvId(mv.id);
                  }}
                />
              ) : createUnderMvId ? (
                <CreateUniverseForm
                  multiverseId={createUnderMvId}
                  onClose={() => setCreateUnderMvId(null)}
                  onCreated={() => {
                    qc.invalidateQueries({ queryKey: ["universes"] });
                    qc.invalidateQueries({ queryKey: ["multiverses"] });
                    setCreateUnderMvId(null);
                  }}
                />
              ) : null}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Tree + detail */}
      <div className="flex-1 overflow-hidden">
        {multiverses.length === 0 && !mvLoading ? (
          <div className="flex flex-col items-center justify-center h-full space-y-3">
            <div className="w-16 h-16 rounded-2xl bg-purple-500/10 border border-purple-500/20 flex items-center justify-center shadow-purple-glow">
              <Layers className="w-8 h-8 text-purple-400" />
            </div>
            <p className="text-sm font-medium text-slate-300">Create a setting first</p>
            <p className="text-xs text-slate-600 text-center max-w-xs">
              Start by creating a multiverse. Universes, stories, and scenes will live inside it.
            </p>
            <button onClick={() => setShowMvForm(true)} className="btn-cyber mt-2">
              <Plus className="w-4 h-4" /> Create Multiverse
            </button>
          </div>
        ) : (
          <UniverseTree
            multiverses={multiverses}
            requestedUniverseId={requestedUniverseId}
            onDeleteUniverse={(id) => deleteUnivMut.mutate(id)}
          />
        )}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
//  ENTITIES TAB (from /npcs)
// ═══════════════════════════════════════════════════════════════

function EntitiesTab() {
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [page, setPage] = useState(0);
  const [activeType, setActiveType] = useState<string | null>(null);
  const LIMIT = 20;

  const ENTITY_TYPE_OPTIONS: Array<{ type: string; icon: React.ElementType; color: string }> = [
    { type: "character", icon: User, color: "text-cyan-300 border-cyan-500/25 bg-cyan-500/8" },
    { type: "location", icon: MapPin, color: "text-amber-400 border-amber-500/25 bg-amber-500/8" },
    { type: "faction", icon: Shield, color: "text-emerald-400 border-emerald-500/25 bg-emerald-500/8" },
    { type: "organization", icon: Users, color: "text-emerald-400 border-emerald-500/25 bg-emerald-500/8" },
    { type: "concept", icon: Sparkles, color: "text-pink-400 border-pink-500/25 bg-pink-500/8" },
    { type: "object", icon: MemoryStick, color: "text-pink-400 border-pink-500/25 bg-pink-500/8" },
    { type: "creature", icon: User, color: "text-amber-400 border-amber-500/25 bg-amber-500/8" },
  ];

  const { data, isLoading } = useQuery({
    queryKey: ["entities", query, page, activeType],
    queryFn: () =>
      entitiesApi.listNPCs({
        q: query || undefined,
        entity_type: activeType ?? undefined,
        limit: LIMIT,
        offset: page * LIMIT,
      }),
    staleTime: 15_000,
  });

  const npcs = data?.items ?? [];
  const total = data?.total ?? 0;

  return (
    <div className="flex-1 flex overflow-hidden">
      <div className="flex-1 overflow-y-auto px-8 py-6 space-y-6">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 className="text-lg font-bold text-slate-100">Entities</h2>
            <p className="text-sm text-slate-500 mt-1">
              {total > 0 ? `${total.toLocaleString()} entities in the knowledge graph.` : "Browse entities stored in the knowledge graph."}
            </p>
          </div>
        </div>

        {/* Type filter chips */}
        <div className="flex items-center gap-2 flex-wrap">
          <button
            onClick={() => { setActiveType(null); setPage(0); }}
            className={cn(
              "text-xs px-3 py-1.5 rounded-lg border transition-all",
              activeType === null
                ? "bg-white/8 border-white/15 text-slate-200"
                : "border-transparent text-slate-600 hover:text-slate-300",
            )}
          >
            All
          </button>
          {ENTITY_TYPE_OPTIONS.map(({ type, icon: Icon, color }) => (
            <button
              key={type}
              onClick={() => { setActiveType(activeType === type ? null : type); setPage(0); }}
              className={cn(
                "flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg border transition-all capitalize",
                activeType === type ? color : "border-transparent text-slate-600 hover:text-slate-300",
              )}
            >
              <Icon className="w-3 h-3" />
              {type}
            </button>
          ))}
        </div>

        <div className="flex gap-3">
          <div className="relative flex-1 max-w-md">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-600" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && (setQuery(search), setPage(0))}
              placeholder="Search by name or description…" aria-label="Search by name or description"
              className="input-cyber pl-9"
            />
          </div>
          <button onClick={() => { setQuery(search); setPage(0); }} className="btn-cyber">
            Search
          </button>
          {(query || activeType) && (
            <button onClick={() => { setSearch(""); setQuery(""); setActiveType(null); setPage(0); }} className="btn-ghost">
              <X className="w-4 h-4" /> Clear
            </button>
          )}
        </div>

        {isLoading && (
          <div className="flex items-center gap-2 text-slate-500 text-sm">
            <Loader2 className="w-4 h-4 animate-spin" /> Querying knowledge graph…
          </div>
        )}

        {npcs.length === 0 && !isLoading && (
          <div className="flex flex-col items-center justify-center py-24 space-y-3">
            <Users className="w-12 h-12 text-slate-700" />
            <p className="text-slate-500 text-sm">
              {query
                ? `No entities matching "${query}".`
                : "No entities found. Ingest source documents to populate the knowledge graph."}
            </p>
          </div>
        )}

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {npcs.map((npc) => (
            <NPCCard key={npc.id} npc={npc} onClick={() => setSelectedId(npc.id)} />
          ))}
        </div>

        {total > LIMIT && (
          <div className="flex items-center justify-center gap-3 pt-4">
            <button
              disabled={page === 0}
              onClick={() => setPage((p) => p - 1)}
              className="btn-ghost disabled:opacity-30"
            >
              Previous
            </button>
            <span className="text-xs text-slate-500">
              Page {page + 1} of {Math.ceil(total / LIMIT)}
            </span>
            <button
              disabled={(page + 1) * LIMIT >= total}
              onClick={() => setPage((p) => p + 1)}
              className="btn-ghost disabled:opacity-30"
            >
              Next
            </button>
          </div>
        )}
      </div>

      <AnimatePresence>
        {selectedId && (
          <NPCDetailPanel npcId={selectedId} onClose={() => setSelectedId(null)} />
        )}
      </AnimatePresence>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
//  MAIN PAGE
// ═══════════════════════════════════════════════════════════════

function WorldsPageContent() {
  const searchParams = useSearchParams();
  // Deep links carrying ?universe= land on the tree so the target is visible
  const [tab, setTab] = useState<WorldTab>(searchParams.get("universe") ? "hierarchy" : "graph");

  return (
    <div className="flex flex-col h-full">
      {/* Header + Tabs */}
      <div className="flex items-center gap-4 px-6 py-3 border-b border-white/5 glass-dark flex-shrink-0">
        <Globe2 className="w-5 h-5 text-purple-400 flex-shrink-0" />
        <h1 className="text-sm font-bold text-slate-200">Worlds</h1>
        <div className="h-5 w-px bg-white/10" />
        <div className="flex items-center gap-1">
          {WORLD_TABS.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              onClick={() => setTab(id)}
              className={cn(
                "flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium transition-all",
                tab === id
                  ? "bg-purple-500/10 text-purple-300 border border-purple-500/25"
                  : "text-slate-500 hover:text-slate-300 border border-transparent",
              )}
            >
              <Icon className="w-3.5 h-3.5" />
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* Tab content */}
      <div className="flex-1 overflow-hidden">
        {tab === "graph" && <GraphTab />}
        {tab === "hierarchy" && <HierarchyTab />}
        {tab === "entities" && <EntitiesTab />}
      </div>
    </div>
  );
}

export default function WorldsPage() {
  return (
    <Suspense fallback={<div className="p-6 text-sm text-slate-500">Loading worlds…</div>}>
      <WorldsPageContent />
    </Suspense>
  );
}
