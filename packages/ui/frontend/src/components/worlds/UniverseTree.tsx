"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { motion, AnimatePresence } from "framer-motion";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  BookOpen,
  ChevronDown,
  ChevronRight,
  Clapperboard,
  Clock,
  Edit2,
  Gamepad2,
  GitBranch,
  Globe2,
  Layers,
  Loader2,
  MessageSquare,
  Network,
  Save,
  Sparkles,
  Trash2,
  Users,
  X,
} from "lucide-react";
import { ApiError, storiesApi, universesApi } from "@/lib/api";
import type {
  Multiverse,
  SceneSummary,
  SceneTurn,
  StorySummary,
  StoryThread,
  Universe,
} from "@/lib/types";
import { cn, formatRelativeTime, truncate } from "@/lib/utils";
import { errorMessage } from "@/lib/errors";
import { repairWorldSelection, useOptionalWorldContext } from "@/lib/world-context";

/** Template visibility filter for universe rows (F3-3 phase 6). */
export type UniverseVisibility = "all" | "playable" | "templates";

function matchesVisibility(u: Universe, visibility: UniverseVisibility): boolean {
  if (visibility === "playable") return !u.is_template;
  if (visibility === "templates") return !!u.is_template;
  return true;
}

// ─────────────────────────────────────────────────────────────
// Selection model: what the detail panel is focused on
// ─────────────────────────────────────────────────────────────

export type TreeSelection =
  | { kind: "universe"; universe: Universe }
  | { kind: "story"; story: StorySummary; universe: Universe | null }
  | { kind: "scene"; scene: SceneSummary; story: StorySummary };

const STORY_STATUS_TAG: Record<string, string> = {
  active: "text-emerald-300 border-emerald-500/30 bg-emerald-500/10",
  completed: "text-cyan-300 border-cyan-500/30 bg-cyan-500/10",
  paused: "text-amber-300 border-amber-500/30 bg-amber-500/10",
  abandoned: "text-slate-400 border-white/10 bg-white/5",
};

function statusTag(status: string): string {
  return STORY_STATUS_TAG[status] ?? "text-slate-400 border-white/10 bg-white/5";
}

// ─────────────────────────────────────────────────────────────
// Tree rows
// ─────────────────────────────────────────────────────────────

function RowChevron({ open }: { open: boolean }) {
  return open ? (
    <ChevronDown className="w-3 h-3 text-slate-600 flex-shrink-0" />
  ) : (
    <ChevronRight className="w-3 h-3 text-slate-600 flex-shrink-0" />
  );
}

function SceneRows({
  story,
  selection,
  onSelect,
}: {
  story: StorySummary;
  selection: TreeSelection | null;
  onSelect: (sel: TreeSelection) => void;
}) {
  const { data: scenes = [], isLoading } = useQuery({
    queryKey: ["story-scenes", story.id],
    queryFn: () => storiesApi.listScenes(story.id),
    staleTime: 15_000,
  });

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 pl-12 py-1.5 text-[11px] text-slate-600">
        <Loader2 className="w-3 h-3 animate-spin" /> scenes…
      </div>
    );
  }
  if (scenes.length === 0) {
    return <div className="pl-12 py-1.5 text-[11px] text-slate-700 italic">No scenes yet</div>;
  }

  return (
    <>
      {scenes.map((scene) => {
        const active = selection?.kind === "scene" && selection.scene.id === scene.id;
        return (
          <button
            key={scene.id}
            onClick={() => onSelect({ kind: "scene", scene, story })}
            className={cn(
              "w-full flex items-center gap-2 pl-12 pr-3 py-1.5 text-left rounded-lg transition-all",
              active ? "bg-amber-500/10 text-amber-200" : "text-slate-500 hover:bg-white/4 hover:text-slate-300",
            )}
          >
            <Clapperboard className="w-3 h-3 flex-shrink-0 text-amber-400/70" />
            <span className="text-[11px] truncate flex-1">{scene.title || "Untitled scene"}</span>
            <span className="text-[10px] text-slate-600 flex-shrink-0">
              {scene.turn_count ?? 0} turns
            </span>
          </button>
        );
      })}
    </>
  );
}

function StoryRows({
  universe,
  selection,
  onSelect,
}: {
  universe: Universe;
  selection: TreeSelection | null;
  onSelect: (sel: TreeSelection) => void;
}) {
  const [openStories, setOpenStories] = useState<Set<string>>(new Set());
  const { data, isLoading } = useQuery({
    queryKey: ["universe-stories", universe.id],
    queryFn: () => storiesApi.listStories({ universe_id: universe.id, limit: 100 }),
    staleTime: 15_000,
  });

  const stories = data?.stories ?? [];

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 pl-9 py-1.5 text-[11px] text-slate-600">
        <Loader2 className="w-3 h-3 animate-spin" /> stories…
      </div>
    );
  }
  if (stories.length === 0) {
    return (
      <div className="pl-9 py-1.5 text-[11px] text-slate-700 italic">
        No stories yet — play a session here to start one
      </div>
    );
  }

  return (
    <>
      {stories.map((story) => {
        const open = openStories.has(story.id);
        const active = selection?.kind === "story" && selection.story.id === story.id;
        return (
          <div key={story.id}>
            <div
              className={cn(
                "group flex items-center gap-2 pl-9 pr-3 py-1.5 rounded-lg cursor-pointer transition-all",
                active ? "bg-purple-500/10 text-purple-200" : "text-slate-400 hover:bg-white/4 hover:text-slate-200",
              )}
              onClick={() => {
                onSelect({ kind: "story", story, universe });
                setOpenStories((prev) => {
                  const next = new Set(prev);
                  if (next.has(story.id)) next.delete(story.id);
                  else next.add(story.id);
                  return next;
                });
              }}
            >
              <RowChevron open={open} />
              <BookOpen className="w-3 h-3 flex-shrink-0 text-purple-400/70" />
              <span className="text-xs truncate flex-1">{story.title}</span>
              <span className={cn("text-[9px] px-1.5 py-px rounded-full border flex-shrink-0", statusTag(story.status))}>
                {story.status}
              </span>
              <span className="text-[10px] text-slate-600 flex-shrink-0">{story.scene_count} sc</span>
            </div>
            {open && <SceneRows story={story} selection={selection} onSelect={onSelect} />}
          </div>
        );
      })}
    </>
  );
}

function UniverseRows({
  multiverseId,
  selection,
  onSelect,
  autoSelectUniverseId,
  visibility = "all",
}: {
  multiverseId: string;
  selection: TreeSelection | null;
  onSelect: (sel: TreeSelection) => void;
  autoSelectUniverseId?: string | null;
  visibility?: UniverseVisibility;
}) {
  const [openUniverses, setOpenUniverses] = useState<Set<string>>(new Set());
  const { data: allUniverses = [], isLoading } = useQuery({
    queryKey: ["universes", multiverseId],
    queryFn: () => universesApi.listUniverses(multiverseId),
    staleTime: 15_000,
  });
  const universes = allUniverses.filter((u) => matchesVisibility(u, visibility));

  // Deep-link: auto-select + expand a requested universe once loaded
  useEffect(() => {
    if (!autoSelectUniverseId) return;
    const u = universes.find((x) => x.id === autoSelectUniverseId);
    if (u && !(selection?.kind === "universe" && selection.universe.id === u.id)) {
      onSelect({ kind: "universe", universe: u });
      setOpenUniverses((prev) => new Set(prev).add(u.id));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoSelectUniverseId, universes.length]);

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 pl-6 py-1.5 text-[11px] text-slate-600">
        <Loader2 className="w-3 h-3 animate-spin" /> universes…
      </div>
    );
  }
  if (universes.length === 0) {
    return (
      <div className="pl-6 py-1.5 text-[11px] text-slate-700 italic">
        {visibility === "all"
          ? "No universes in this setting"
          : visibility === "templates"
            ? "No template universes in this setting"
            : "No playable universes in this setting"}
      </div>
    );
  }

  return (
    <>
      {universes.map((u) => {
        const open = openUniverses.has(u.id);
        const active = selection?.kind === "universe" && selection.universe.id === u.id;
        return (
          <div key={u.id}>
            <div
              className={cn(
                "group flex items-center gap-2 pl-6 pr-3 py-2 rounded-lg cursor-pointer transition-all",
                active ? "bg-cyan-500/10 text-cyan-200" : "text-slate-300 hover:bg-white/4",
              )}
              onClick={() => {
                onSelect({ kind: "universe", universe: u });
                setOpenUniverses((prev) => {
                  const next = new Set(prev);
                  if (next.has(u.id)) next.delete(u.id);
                  else next.add(u.id);
                  return next;
                });
              }}
            >
              <RowChevron open={open} />
              <Globe2 className="w-3.5 h-3.5 flex-shrink-0 text-cyan-400/80" />
              <span className="text-xs font-medium truncate flex-1">{u.name}</span>
              {u.is_template && (
                <span className="text-[9px] px-1.5 py-px rounded-full border border-amber-500/30 bg-amber-500/10 text-amber-300 flex-shrink-0">
                  Template
                </span>
              )}
              <span className="text-[10px] text-slate-600 flex-shrink-0">
                {(u.story_count ?? 0)} stories · {u.entity_count} ent
              </span>
            </div>
            {open && <StoryRows universe={u} selection={selection} onSelect={onSelect} />}
          </div>
        );
      })}
    </>
  );
}

// ─────────────────────────────────────────────────────────────
// Edit forms (F3-3 phases 4–5)
// ─────────────────────────────────────────────────────────────

function MultiverseEditForm({ mv, onClose }: { mv: Multiverse; onClose: () => void }) {
  const qc = useQueryClient();
  const [name, setName] = useState(mv.name);
  const [systemName, setSystemName] = useState(mv.system_name ?? "");
  const [desc, setDesc] = useState(mv.description ?? "");

  const mut = useMutation({
    mutationFn: () =>
      universesApi.updateMultiverse(mv.id, {
        name: name.trim(),
        // Empty strings would fail backend min_length=1 — omit instead.
        description: desc.trim() || undefined,
        system_name: systemName.trim() || undefined,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["multiverses"] });
      onClose();
    },
  });

  return (
    <div className="mx-2 my-1.5 glass-dark rounded-xl border border-purple-500/20 p-3 space-y-2">
      <div className="flex items-center justify-between">
        <p className="text-[11px] font-semibold text-purple-300">Edit multiverse</p>
        <button onClick={onClose} aria-label="Close edit form" className="text-slate-600 hover:text-slate-300">
          <X className="w-3 h-3" />
        </button>
      </div>
      <input
        className="input-cyber w-full py-1.5 text-xs"
        placeholder="Name…"
        aria-label="Multiverse name"
        value={name}
        onChange={(e) => setName(e.target.value)}
        autoFocus
      />
      <input
        className="input-cyber w-full py-1.5 text-xs"
        placeholder="Game system (optional, e.g. D&D 5e)"
        aria-label="Game system"
        value={systemName}
        onChange={(e) => setSystemName(e.target.value)}
      />
      <input
        className="input-cyber w-full py-1.5 text-xs"
        placeholder="Description (optional)"
        aria-label="Multiverse description"
        value={desc}
        onChange={(e) => setDesc(e.target.value)}
      />
      {mut.isError && <p className="text-[11px] text-red-400">{errorMessage(mut.error)}</p>}
      <button
        onClick={() => mut.mutate()}
        disabled={!name.trim() || mut.isPending}
        className="btn-cyber w-full justify-center text-xs py-1.5 disabled:opacity-50"
      >
        {mut.isPending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
        Save
      </button>
    </div>
  );
}

function UniverseEditForm({ universe, onClose }: { universe: Universe; onClose: () => void }) {
  const qc = useQueryClient();
  const [name, setName] = useState(universe.name);
  const [genre, setGenre] = useState(universe.genre ?? "");
  const [tone, setTone] = useState(universe.tone ?? "");
  const [desc, setDesc] = useState(universe.description ?? "");

  const mut = useMutation({
    mutationFn: () =>
      universesApi.updateUniverse(universe.id, {
        name: name.trim(),
        genre: genre.trim() || undefined,
        tone: tone.trim() || undefined,
        description: desc.trim() || undefined,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["universe", universe.id] });
      qc.invalidateQueries({ queryKey: ["universes"] });
      onClose();
    },
  });

  return (
    <div className="glass-dark rounded-xl border border-cyan-500/20 p-3 space-y-2">
      <div className="flex items-center justify-between">
        <p className="text-[11px] font-semibold text-cyan-300">Edit universe</p>
        <button onClick={onClose} aria-label="Close edit form" className="text-slate-600 hover:text-slate-300">
          <X className="w-3 h-3" />
        </button>
      </div>
      <input
        className="input-cyber w-full py-1.5 text-xs"
        placeholder="Name…"
        aria-label="Universe name"
        value={name}
        onChange={(e) => setName(e.target.value)}
        autoFocus
      />
      <div className="grid grid-cols-2 gap-2">
        <input
          className="input-cyber w-full py-1.5 text-xs"
          placeholder="Genre (e.g. fantasy)"
          aria-label="Genre"
          value={genre}
          onChange={(e) => setGenre(e.target.value)}
        />
        <input
          className="input-cyber w-full py-1.5 text-xs"
          placeholder="Tone (e.g. dark)"
          aria-label="Tone"
          value={tone}
          onChange={(e) => setTone(e.target.value)}
        />
      </div>
      <textarea
        className="input-cyber w-full py-1.5 text-xs"
        placeholder="Description (optional)"
        aria-label="Universe description"
        rows={3}
        value={desc}
        onChange={(e) => setDesc(e.target.value)}
      />
      {mut.isError && <p className="text-[11px] text-red-400">{errorMessage(mut.error)}</p>}
      <button
        onClick={() => mut.mutate()}
        disabled={!name.trim() || mut.isPending}
        className="btn-cyber w-full justify-center text-xs py-1.5 disabled:opacity-50"
      >
        {mut.isPending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
        Save
      </button>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
// Detail panels
// ─────────────────────────────────────────────────────────────

function UniverseDetail({ universe, onDelete }: { universe: Universe; onDelete?: (id: string) => void }) {
  const qc = useQueryClient();
  const [editing, setEditing] = useState(false);
  // Re-fetch for live counts (tree rows may hold a stale list entry)
  const { data: fresh } = useQuery({
    queryKey: ["universe", universe.id],
    queryFn: () => universesApi.getUniverse(universe.id),
    staleTime: 10_000,
  });
  const u = fresh ?? universe;

  // Seed from tables (F1-5b) — blank-world onramp for empty universes (M-33)
  const seedMut = useMutation({
    mutationFn: () => universesApi.seedUniverse(u.id, { entity_count: 10, use_tables: true }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["universe", u.id] });
      qc.invalidateQueries({ queryKey: ["universes"] });
    },
  });
  const showSeed = u.entity_count === 0 || seedMut.isSuccess;

  return (
    <div className="space-y-5">
      <div className="flex items-start gap-3">
        <div className="w-10 h-10 rounded-xl bg-cyan-500/10 border border-cyan-500/25 flex items-center justify-center flex-shrink-0">
          <Globe2 className="w-5 h-5 text-cyan-400" />
        </div>
        <div className="min-w-0 flex-1">
          <h2 className="text-base font-semibold text-slate-100 truncate">{u.name}</h2>
          <div className="flex items-center gap-2 mt-1 flex-wrap">
            {u.is_template && (
              <span className="text-[10px] px-1.5 py-px rounded-full border border-amber-500/30 bg-amber-500/10 text-amber-300">
                Template
              </span>
            )}
            {u.genre && <span className="tag-purple text-[10px]">{u.genre}</span>}
            {u.tone && <span className="tag-dim text-[10px]">{u.tone}</span>}
            {u.tags.map((t) => (
              <span key={t} className="tag-dim text-[10px]">{t}</span>
            ))}
          </div>
        </div>
        <button
          onClick={() => setEditing((v) => !v)}
          aria-label="Edit universe"
          title="Edit universe"
          className={cn(
            "p-1.5 rounded-lg transition-all flex-shrink-0",
            editing ? "text-cyan-300 bg-cyan-500/10" : "text-slate-600 hover:text-slate-300 hover:bg-white/5",
          )}
        >
          <Edit2 className="w-3.5 h-3.5" />
        </button>
      </div>

      {editing ? (
        <UniverseEditForm universe={u} onClose={() => setEditing(false)} />
      ) : (
        u.description && <p className="text-xs text-slate-400 leading-relaxed">{u.description}</p>
      )}

      <div className="grid grid-cols-3 gap-2">
        {[
          { label: "Entities", value: u.entity_count, icon: Users },
          { label: "Stories", value: u.story_count ?? 0, icon: BookOpen },
          { label: "Sessions", value: u.session_count, icon: MessageSquare },
        ].map(({ label, value, icon: Icon }) => (
          <div key={label} className="glass-dark rounded-xl border border-white/5 px-3 py-2.5 text-center">
            <Icon className="w-3.5 h-3.5 text-slate-600 mx-auto mb-1" />
            <p className="text-lg font-bold font-mono text-slate-200">{value}</p>
            <p className="text-[10px] text-slate-600">{label}</p>
          </div>
        ))}
      </div>

      {showSeed && (
        <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/5 p-3 space-y-2">
          <p className="text-[10px] uppercase tracking-wider text-emerald-400 font-bold flex items-center gap-1.5">
            <Sparkles className="w-3 h-3" /> Empty world
          </p>
          {seedMut.isSuccess ? (
            <div className="text-[11px] space-y-1">
              <p className="text-emerald-300">
                Seeded {seedMut.data.entities_created} entities from random tables.
              </p>
              {seedMut.data.errors.length > 0 && (
                <p className="text-amber-400">
                  {seedMut.data.errors.length} error{seedMut.data.errors.length !== 1 ? "s" : ""}: {seedMut.data.errors[0]}
                </p>
              )}
            </div>
          ) : (
            <>
              <p className="text-[11px] text-slate-500 leading-relaxed">
                This universe has no entities yet. Seed it with content generated from your random tables.
              </p>
              <button
                onClick={() => seedMut.mutate()}
                disabled={seedMut.isPending}
                className="btn-cyber text-xs py-1.5 disabled:opacity-50"
              >
                {seedMut.isPending ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                ) : (
                  <Sparkles className="w-3.5 h-3.5" />
                )}
                Seed from tables
              </button>
              {seedMut.isError && (
                <p className="text-[11px] text-red-400">{errorMessage(seedMut.error)}</p>
              )}
            </>
          )}
        </div>
      )}

      <div className="space-y-2">
        <p className="text-[10px] text-slate-600 uppercase tracking-wider">Jump in</p>
        <div className="grid grid-cols-2 gap-2">
          <Link
            href={`/play?universe=${u.id}&multiverse=${u.multiverse_id}`}
            className="btn-cyber justify-center text-xs py-2"
          >
            <Gamepad2 className="w-3.5 h-3.5" /> Play here
          </Link>
          <Link
            href={`/explorer?universe=${u.id}`}
            className="btn-ghost justify-center text-xs py-2 border border-white/10"
          >
            <Network className="w-3.5 h-3.5" /> Explore graph
          </Link>
          <Link
            href={`/forge/snapshots?universe=${u.id}`}
            className="btn-ghost justify-center text-xs py-2 border border-white/10"
          >
            <Clock className="w-3.5 h-3.5" /> Snapshots
          </Link>
          <Link
            href={`/gm?universe=${u.id}`}
            className="btn-ghost justify-center text-xs py-2 border border-white/10"
          >
            <Sparkles className="w-3.5 h-3.5" /> GM tools
          </Link>
        </div>
      </div>

      <div className="flex items-center justify-between pt-2 border-t border-white/5">
        <p className="text-[10px] text-slate-700 font-mono break-all">{u.id}</p>
        {onDelete && (
          <button
            onClick={() => {
              if (window.confirm(`Delete universe “${u.name}” and all its canon? This cannot be undone.`)) {
                onDelete(u.id);
              }
            }}
            className="btn-danger text-xs py-1 px-2.5 flex-shrink-0 ml-3"
          >
            Delete
          </button>
        )}
      </div>
    </div>
  );
}

function StoryDetail({
  story,
  onSelectScene,
}: {
  story: StorySummary;
  onSelectScene: (scene: SceneSummary) => void;
}) {
  const { data: arc } = useQuery({
    queryKey: ["story", story.id],
    queryFn: () => storiesApi.getStory(story.id),
    staleTime: 15_000,
    retry: 1,
  });
  const { data: threads = [] } = useQuery({
    queryKey: ["story-threads", story.id],
    queryFn: () => storiesApi.listThreads(story.id),
    staleTime: 30_000,
    retry: 1,
  });
  const { data: scenes = [] } = useQuery({
    queryKey: ["story-scenes", story.id],
    queryFn: () => storiesApi.listScenes(story.id),
    staleTime: 15_000,
  });

  const tension = arc?.tension_score ?? 0.5;

  return (
    <div className="space-y-5">
      <div className="flex items-start gap-3">
        <div className="w-10 h-10 rounded-xl bg-purple-500/10 border border-purple-500/25 flex items-center justify-center flex-shrink-0">
          <BookOpen className="w-5 h-5 text-purple-400" />
        </div>
        <div className="min-w-0 flex-1">
          <h2 className="text-base font-semibold text-slate-100 leading-tight">{story.title}</h2>
          <div className="flex items-center gap-2 mt-1 flex-wrap">
            <span className={cn("text-[10px] px-1.5 py-px rounded-full border", statusTag(story.status))}>
              {story.status}
            </span>
            <span className="tag-dim text-[10px] capitalize">{story.story_type}</span>
            {arc?.arc_label && <span className="tag-purple text-[10px]">{arc.arc_label}</span>}
          </div>
        </div>
      </div>

      {story.premise && (
        <p className="text-xs text-slate-400 leading-relaxed">{truncate(story.premise, 280)}</p>
      )}

      {/* Tension meter */}
      {arc && (
        <div className="space-y-1.5">
          <div className="flex items-center justify-between text-[10px] uppercase tracking-wider font-bold">
            <span className="flex items-center gap-1.5 text-slate-500">
              <Activity className="w-3 h-3 text-purple-400" /> Narrative tension
            </span>
            <span className="font-mono text-slate-400">{(tension * 10).toFixed(1)}/10</span>
          </div>
          <div className="h-1.5 w-full bg-white/5 rounded-full overflow-hidden">
            <div
              className={cn(
                "h-full rounded-full",
                tension > 0.7 ? "bg-red-500/80" : tension > 0.4 ? "bg-amber-500/80" : "bg-emerald-500/80",
              )}
              style={{ width: `${Math.min(100, Math.max(0, tension * 100))}%` }}
            />
          </div>
        </div>
      )}

      {/* Threads */}
      <div className="space-y-2">
        <p className="text-[10px] text-slate-600 uppercase tracking-wider flex items-center gap-1.5">
          <GitBranch className="w-3 h-3" /> Open threads
        </p>
        {threads.length === 0 && (arc?.active_threads?.length ?? 0) === 0 ? (
          <p className="text-[11px] text-slate-700 italic">No tracked threads</p>
        ) : (
          <div className="space-y-1">
            {(threads.length > 0
              ? threads.map((t: StoryThread) => t.title)
              : arc?.active_threads ?? []
            ).slice(0, 6).map((title, i) => (
              <div key={`${title}-${i}`} className="flex items-start gap-2 text-xs text-slate-300 bg-white/4 rounded-lg px-2.5 py-1.5">
                <span className="mt-1 w-1.5 h-1.5 rounded-full bg-purple-400/60 flex-shrink-0" />
                {title}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Scene timeline */}
      <div className="space-y-2">
        <p className="text-[10px] text-slate-600 uppercase tracking-wider flex items-center gap-1.5">
          <Clapperboard className="w-3 h-3" /> Scenes ({scenes.length})
        </p>
        {scenes.length === 0 ? (
          <p className="text-[11px] text-slate-700 italic">No scenes recorded yet</p>
        ) : (
          <div className="space-y-1.5">
            {scenes.map((sc, i) => (
              <button
                key={sc.id}
                onClick={() => onSelectScene(sc)}
                className="w-full text-left glass-dark rounded-xl border border-white/5 hover:border-amber-500/25 px-3 py-2 transition-all"
              >
                <div className="flex items-center gap-2">
                  <span className="text-[10px] font-mono text-slate-600 flex-shrink-0">#{i + 1}</span>
                  <span className="text-xs text-slate-200 truncate flex-1">{sc.title || "Untitled scene"}</span>
                  <span className={cn("text-[9px] px-1.5 py-px rounded-full border flex-shrink-0", statusTag(sc.status))}>
                    {sc.status}
                  </span>
                </div>
                {sc.summary && (
                  <p className="text-[11px] text-slate-500 mt-1 leading-relaxed">{truncate(sc.summary, 140)}</p>
                )}
                <div className="text-[10px] text-slate-600 mt-1">
                  {sc.turn_count ?? 0} turns · {formatRelativeTime(sc.updated_at)}
                </div>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function SceneDetail({ scene, story }: { scene: SceneSummary; story: StorySummary }) {
  const { data: turns = [], isLoading } = useQuery({
    queryKey: ["scene-turns", scene.id],
    queryFn: () => storiesApi.getSceneTurns(scene.id, 30),
    staleTime: 10_000,
  });

  return (
    <div className="space-y-5">
      <div className="flex items-start gap-3">
        <div className="w-10 h-10 rounded-xl bg-amber-500/10 border border-amber-500/25 flex items-center justify-center flex-shrink-0">
          <Clapperboard className="w-5 h-5 text-amber-400" />
        </div>
        <div className="min-w-0">
          <h2 className="text-base font-semibold text-slate-100 leading-tight">
            {scene.title || "Untitled scene"}
          </h2>
          <p className="text-[11px] text-slate-600 mt-0.5">in “{story.title}”</p>
          <div className="flex items-center gap-2 mt-1">
            <span className={cn("text-[10px] px-1.5 py-px rounded-full border", statusTag(scene.status))}>
              {scene.status}
            </span>
            <span className="text-[10px] text-slate-600">{scene.turn_count ?? 0} turns</span>
          </div>
        </div>
      </div>

      {scene.purpose && <p className="text-xs text-slate-500 italic leading-relaxed">{scene.purpose}</p>}
      {scene.summary && <p className="text-xs text-slate-400 leading-relaxed">{scene.summary}</p>}

      <div className="space-y-2">
        <p className="text-[10px] text-slate-600 uppercase tracking-wider">Transcript (last {turns.length})</p>
        {isLoading ? (
          <div className="flex items-center gap-2 py-4 text-slate-600 text-xs">
            <Loader2 className="w-3.5 h-3.5 animate-spin" /> Loading turns…
          </div>
        ) : turns.length === 0 ? (
          <p className="text-[11px] text-slate-700 italic">No turns recorded</p>
        ) : (
          <div className="space-y-2">
            {turns.map((t: SceneTurn, i) => {
              const isGM = (t.speaker ?? "").toLowerCase() === "gm";
              return (
                <div
                  key={t.turn_id ?? i}
                  className={cn(
                    "rounded-xl px-3 py-2 text-xs leading-relaxed border",
                    isGM
                      ? "bg-purple-500/5 border-purple-500/15 text-slate-300"
                      : "bg-cyan-500/5 border-cyan-500/15 text-slate-300",
                  )}
                >
                  <div className={cn("text-[10px] font-semibold mb-0.5", isGM ? "text-purple-400" : "text-cyan-400")}>
                    {isGM ? "GM" : t.speaker || "Player"}
                  </div>
                  {truncate(t.text, 400)}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
// Main component: tree + detail panel
// ─────────────────────────────────────────────────────────────

export function UniverseTree({
  multiverses,
  requestedUniverseId,
  onDeleteUniverse,
}: {
  multiverses: Multiverse[];
  requestedUniverseId?: string | null;
  onDeleteUniverse?: (id: string) => void;
}) {
  const qc = useQueryClient();
  const world = useOptionalWorldContext();
  const [openMultiverses, setOpenMultiverses] = useState<Set<string>>(new Set());
  const [selection, setSelection] = useState<TreeSelection | null>(null);
  const [visibility, setVisibility] = useState<UniverseVisibility>("all");
  const [editingMvId, setEditingMvId] = useState<string | null>(null);
  const [mvError, setMvError] = useState<{ id: string; message: string } | null>(null);

  // Deep-link: find which multiverse owns ?universe= and expand it
  const { data: requestedUniverse } = useQuery({
    queryKey: ["universe", requestedUniverseId],
    queryFn: () => universesApi.getUniverse(requestedUniverseId!),
    enabled: !!requestedUniverseId,
  });

  // Safe multiverse delete (F3-3 phase 2/4): the backend refuses non-empty
  // settings with 409 — surface that instead of cascading.
  const deleteMvMut = useMutation({
    mutationFn: (id: string) => universesApi.deleteMultiverse(id),
    onSuccess: (_data, id) => {
      setMvError(null);
      qc.invalidateQueries({ queryKey: ["multiverses"] });
      qc.invalidateQueries({ queryKey: ["universes", id] });
      // Repair the persisted world selection if it pointed at this setting.
      if (world) world.setWorld(repairWorldSelection(world, { multiverseId: id }));
    },
    onError: (err, id) => {
      setMvError({
        id,
        message:
          err instanceof ApiError && err.status === 409
            ? "This setting still contains universes — delete or move them first."
            : errorMessage(err),
      });
    },
  });

  useEffect(() => {
    if (requestedUniverse?.multiverse_id) {
      setOpenMultiverses((prev) => new Set(prev).add(requestedUniverse.multiverse_id));
    } else if (multiverses.length > 0 && openMultiverses.size === 0) {
      setOpenMultiverses(new Set([multiverses[0].id]));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [requestedUniverse?.multiverse_id, multiverses.length]);

  return (
    <div className="flex h-full overflow-hidden">
      {/* Tree */}
      <div className="w-[380px] flex-shrink-0 border-r border-white/5 overflow-y-auto py-3 px-2 space-y-0.5">
        {/* Template visibility filter (F3-3 phase 6) */}
        <div className="flex items-center gap-2 px-3 pb-2">
          <label htmlFor="universe-visibility" className="text-[10px] text-slate-600 uppercase tracking-wider">
            Show
          </label>
          <select
            id="universe-visibility"
            value={visibility}
            onChange={(e) => setVisibility(e.target.value as UniverseVisibility)}
            className="input-cyber py-1 text-xs flex-1"
          >
            <option value="all">All universes</option>
            <option value="playable">Playable only</option>
            <option value="templates">Templates only</option>
          </select>
        </div>
        {multiverses.length === 0 && (
          <div className="px-4 py-10 text-center space-y-2">
            <Layers className="w-8 h-8 mx-auto text-slate-700" />
            <p className="text-xs text-slate-500">No settings yet — create a multiverse to begin.</p>
          </div>
        )}
        {multiverses.map((mv) => {
          const open = openMultiverses.has(mv.id);
          return (
            <div key={mv.id}>
              <div
                className={cn(
                  "group flex items-center gap-2 px-3 py-2 rounded-lg cursor-pointer transition-all",
                  "text-slate-200 hover:bg-white/4",
                )}
                onClick={() =>
                  setOpenMultiverses((prev) => {
                    const next = new Set(prev);
                    if (next.has(mv.id)) next.delete(mv.id);
                    else next.add(mv.id);
                    return next;
                  })
                }
              >
                <RowChevron open={open} />
                <Layers className="w-3.5 h-3.5 flex-shrink-0 text-purple-400" />
                <span className="text-xs font-semibold truncate flex-1">{mv.name}</span>
                {mv.is_template && (
                  <span className="text-[9px] px-1.5 py-px rounded-full border border-amber-500/30 bg-amber-500/10 text-amber-300 flex-shrink-0">
                    Template
                  </span>
                )}
                <span className="text-[10px] text-slate-600 flex-shrink-0">
                  {mv.universe_count} universe{mv.universe_count !== 1 ? "s" : ""}
                </span>
                <span className="hidden group-hover:flex items-center gap-0.5 flex-shrink-0">
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      setMvError(null);
                      setEditingMvId(editingMvId === mv.id ? null : mv.id);
                    }}
                    aria-label={`Edit ${mv.name}`}
                    title="Edit multiverse"
                    className="p-1 rounded text-slate-600 hover:text-slate-200 hover:bg-white/10"
                  >
                    <Edit2 className="w-3 h-3" />
                  </button>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      if (
                        window.confirm(
                          `Delete setting “${mv.name}”? It contains ${mv.universe_count} universe${mv.universe_count !== 1 ? "s" : ""}. This cannot be undone.`,
                        )
                      ) {
                        deleteMvMut.mutate(mv.id);
                      }
                    }}
                    aria-label={`Delete ${mv.name}`}
                    title="Delete multiverse"
                    className="p-1 rounded text-slate-600 hover:text-red-300 hover:bg-red-500/10"
                  >
                    <Trash2 className="w-3 h-3" />
                  </button>
                </span>
              </div>
              {mvError?.id === mv.id && (
                <p role="alert" className="mx-3 my-1 text-[11px] text-red-400">
                  {mvError.message}
                </p>
              )}
              {editingMvId === mv.id && (
                <MultiverseEditForm mv={mv} onClose={() => setEditingMvId(null)} />
              )}
              {open && (
                <UniverseRows
                  multiverseId={mv.id}
                  selection={selection}
                  onSelect={setSelection}
                  visibility={visibility}
                  autoSelectUniverseId={
                    requestedUniverse?.multiverse_id === mv.id ? requestedUniverseId : null
                  }
                />
              )}
            </div>
          );
        })}
      </div>

      {/* Detail panel */}
      <div className="flex-1 overflow-y-auto px-6 py-5">
        <AnimatePresence mode="wait">
          <motion.div
            key={
              selection
                ? `${selection.kind}-${selection.kind === "universe" ? selection.universe.id : selection.kind === "story" ? selection.story.id : selection.scene.id}`
                : "empty"
            }
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            transition={{ duration: 0.12 }}
            className="max-w-xl"
          >
            {!selection ? (
              <div className="flex flex-col items-center justify-center py-24 text-center space-y-3">
                <Globe2 className="w-10 h-10 text-slate-800" />
                <p className="text-sm text-slate-500">Select a universe, story, or scene</p>
                <p className="text-xs text-slate-700 max-w-xs leading-relaxed">
                  Expand the tree to traverse your settings — every story and scene played in a
                  universe lives here.
                </p>
              </div>
            ) : selection.kind === "universe" ? (
              <UniverseDetail universe={selection.universe} onDelete={onDeleteUniverse} />
            ) : selection.kind === "story" ? (
              <StoryDetail
                story={selection.story}
                onSelectScene={(scene) => setSelection({ kind: "scene", scene, story: selection.story })}
              />
            ) : (
              <SceneDetail scene={selection.scene} story={selection.story} />
            )}
          </motion.div>
        </AnimatePresence>
      </div>
    </div>
  );
}
