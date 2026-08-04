"use client";

import { useState } from "react";
import { Loader2, Pencil, Plus, Sparkles, Trash2 } from "lucide-react";
import type { Session } from "@/lib/types";
import { cn, formatRelativeTime } from "@/lib/utils";

const MODE_LABEL: Record<string, string> = {
  autonomous_gm: "Autonomous GM",
  gm_assistant: "GM Assistant",
  world_architect: "World Architect",
};

const PHASE_DOT: Record<string, string> = {
  active_play: "bg-emerald-400",
  awaiting_character: "bg-amber-400",
  awaiting_premise: "bg-amber-400",
  setup: "bg-amber-400",
  scene_end: "bg-cyan-400",
  scene_ended: "bg-cyan-400",
};

export interface SessionListProps {
  sessions: Session[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
  onDelete: (id: string) => void;
  onRename: (id: string, title: string) => void;
  loading: boolean;
}

export function SessionList({
  sessions,
  activeId,
  onSelect,
  onNew,
  onDelete,
  onRename,
  loading,
}: SessionListProps) {
  const [filter, setFilter] = useState("");
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");

  const visible = filter.trim()
    ? sessions.filter((s) =>
        `${s.title} ${s.universe_label ?? ""} ${s.speaker_label ?? ""}`
          .toLowerCase()
          .includes(filter.trim().toLowerCase()),
      )
    : sessions;

  const commitRename = (id: string) => {
    const title = renameValue.trim();
    setRenamingId(null);
    if (title) onRename(id, title);
  };

  return (
    <div className="glass flex flex-col border-r border-white/5 w-72 flex-shrink-0">
      <div className="flex items-center justify-between px-4 py-4 border-b border-white/5">
        <div>
          <span className="text-xs font-semibold text-slate-500 tracking-widest uppercase">
            Play Sessions
          </span>
          <p className="text-[10px] text-slate-700 mt-0.5">New or continue a story</p>
        </div>
        <button
          onClick={onNew}
          className="w-8 h-8 flex items-center justify-center rounded-lg border border-cyan-500/40 bg-cyan-500/10 text-cyan-300 hover:bg-cyan-500/20 hover:border-cyan-500/60 transition-all shadow-sm hover:shadow-cyan-glow"
          title="New session"
          aria-label="New session"
        >
          <Plus className="w-4 h-4" />
        </button>
      </div>

      <div className="px-3 py-3 border-b border-white/5 space-y-2">
        <button onClick={onNew} className="btn-cyber w-full justify-center text-xs">
          <Sparkles className="w-3.5 h-3.5" />
          Start New Session
        </button>
        {sessions.length > 5 && (
          <input
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="Filter sessions…"
            className="w-full bg-slate-900/60 border border-white/10 rounded-lg px-2.5 py-1.5 text-[11px] text-slate-200 placeholder:text-slate-600 focus:outline-none focus:border-cyan-500/40"
          />
        )}
      </div>

      <div className="flex-1 overflow-y-auto py-2 px-2 space-y-1">
        {loading && (
          <div className="flex items-center gap-2 px-3 py-2 text-slate-600 text-xs">
            <Loader2 className="w-3 h-3 animate-spin" />
            Loading…
          </div>
        )}

        {sessions.length === 0 && !loading && (
          <div className="flex flex-col items-center justify-center py-10 px-6 text-center">
            <div className="w-14 h-14 rounded-2xl bg-cyan-500/8 border border-cyan-500/15 flex items-center justify-center mb-4">
              <Sparkles className="w-6 h-6 text-cyan-500/40" />
            </div>
            <p className="text-xs text-slate-400 font-medium mb-1">No sessions yet</p>
            <p className="text-[11px] text-slate-600 leading-relaxed">
              Click &quot;Start New Session&quot; above, or pick a benchmark to begin.
            </p>
          </div>
        )}

        {visible.length === 0 && sessions.length > 0 && !loading && (
          <p className="px-3 py-4 text-[11px] text-slate-600 text-center">
            No sessions match &ldquo;{filter.trim()}&rdquo;.
          </p>
        )}

        {visible.map((s) => (
          <div
            key={s.id}
            className={cn(
              "group relative rounded-lg border transition-all duration-150",
              activeId === s.id
                ? "bg-cyan-500/8 border-cyan-500/20"
                : "border-transparent hover:bg-white/4",
            )}
          >
            {renamingId === s.id ? (
              <div className="px-3 py-3">
                <input
                  autoFocus
                  value={renameValue}
                  onChange={(e) => setRenameValue(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") commitRename(s.id);
                    if (e.key === "Escape") setRenamingId(null);
                  }}
                  onBlur={() => commitRename(s.id)}
                  className="w-full bg-slate-900/70 border border-cyan-500/40 rounded px-2 py-1 text-xs text-slate-100 focus:outline-none"
                />
              </div>
            ) : (
              <>
                <button
                  onClick={() => onSelect(s.id)}
                  onDoubleClick={() => {
                    setRenamingId(s.id);
                    setRenameValue(s.title);
                  }}
                  className="w-full text-left px-3 py-3 pr-14"
                  title="Double-click to rename"
                >
                  <div className="flex items-center gap-1.5 min-w-0">
                    <span
                      className={cn(
                        "w-1.5 h-1.5 rounded-full flex-shrink-0",
                        PHASE_DOT[s.phase ?? ""] ?? "bg-slate-600",
                      )}
                      title={`Phase: ${(s.phase ?? "unknown").replace(/_/g, " ")}`}
                    />
                    <span
                      className={cn(
                        "text-xs font-medium truncate",
                        activeId === s.id
                          ? "text-cyan-300"
                          : "text-slate-400 group-hover:text-slate-200",
                      )}
                    >
                      {s.title}
                    </span>
                  </div>
                  <div className="text-[10px] text-slate-600 mt-0.5">
                    {(MODE_LABEL[s.mode] ?? s.mode).replace(/_/g, " ")}
                  </div>
                  <div className="text-[10px] text-slate-600 mt-1 space-y-0.5">
                    {(s.universe_label ?? s.world_id) && (
                      <div>Universe: {s.universe_label ?? "Bound"}</div>
                    )}
                    {s.speaker_label && <div>Speaker: {s.speaker_label}</div>}
                    {s.benchmark_label && <div>Benchmark: {s.benchmark_label}</div>}
                    <div>{formatRelativeTime(s.updated_at)}</div>
                  </div>
                </button>
                <div className="absolute top-2.5 right-2 flex items-center gap-0.5 opacity-50 group-hover:opacity-100 transition-all">
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      setRenamingId(s.id);
                      setRenameValue(s.title);
                    }}
                    className="w-7 h-7 flex items-center justify-center rounded-md border border-white/10 text-slate-500 hover:text-cyan-300 hover:border-cyan-500/40 hover:bg-cyan-500/10 bg-slate-900/40"
                    title="Rename session"
                    aria-label="Rename session"
                  >
                    <Pencil className="w-3.5 h-3.5" />
                  </button>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      if (
                        window.confirm(
                          `Delete session "${s.title}"? Its chat transcript is removed; canon already accepted stays in the world.`,
                        )
                      ) {
                        onDelete(s.id);
                      }
                    }}
                    className="w-7 h-7 flex items-center justify-center rounded-md border border-white/10 text-slate-500 hover:text-red-400 hover:border-red-500/40 hover:bg-red-500/10 bg-slate-900/40"
                    title="Delete session"
                    aria-label="Delete session"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              </>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}