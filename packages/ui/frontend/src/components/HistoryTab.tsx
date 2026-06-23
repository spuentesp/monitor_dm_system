"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { History, Loader2, ScrollText } from "lucide-react";
import { changeLogApi } from "@/lib/api";
import type { ChangeLogEntry } from "@/lib/types";
import { cn, formatRelativeTime } from "@/lib/utils";
import { changeIcon, changeColor } from "@/lib/historyMapping";

/**
 * Q-10 audit trail (T-064). Read-only timeline of every canonical change
 * CanonKeeper has committed, newest first. Filterable by subject type.
 */

const SUBJECT_TYPES = [
  "", "entity", "fact", "lore_event", "axiom", "relationship", "event", "story", "scene",
] as const;

function EntryRow({ entry }: { entry: ChangeLogEntry }) {
  const Icon = changeIcon(entry.change_type);
  return (
    <div className="flex gap-3 px-3 py-2.5 rounded-lg hover:bg-white/5 transition-colors">
      <div className={cn("mt-0.5", changeColor(entry.change_type))}>
        <Icon className="w-4 h-4" />
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-xs font-semibold text-slate-200 capitalize">
            {entry.change_type.replace(/_/g, " ")}
          </span>
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-white/5 text-slate-400 uppercase tracking-wide">
            {entry.subject_type}
          </span>
          {entry.field_path && (
            <span className="text-[10px] font-mono text-slate-500">{entry.field_path}</span>
          )}
        </div>
        {entry.reason && (
          <p className="text-[11px] text-slate-400 mt-0.5 leading-relaxed line-clamp-2">{entry.reason}</p>
        )}
        <div className="flex items-center gap-2 mt-1 text-[10px] text-slate-600">
          <span>{entry.author}</span>
          <span>·</span>
          <span className="capitalize">{entry.authority}</span>
          <span>·</span>
          <span className="font-mono">{entry.subject_id.slice(0, 8)}</span>
          <span className="ml-auto">{formatRelativeTime(entry.timestamp)}</span>
        </div>
      </div>
    </div>
  );
}

export function HistoryTab() {
  const [subjectType, setSubjectType] = useState<string>("");
  const q = useQuery({
    queryKey: ["change-log", subjectType],
    queryFn: () =>
      changeLogApi.list({ subject_type: subjectType || undefined, limit: 200 }),
    refetchInterval: 15000,
  });

  const entries = q.data?.entries ?? [];

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-slate-200">
          <History className="w-4 h-4 text-cyan-400" />
          <h2 className="text-sm font-semibold">Canon History</h2>
          {q.data && (
            <span className="text-[10px] px-2 py-0.5 rounded-full bg-white/5 text-slate-500 font-mono">
              {q.data.total}
            </span>
          )}
        </div>
        <div className="flex flex-wrap gap-1">
          {SUBJECT_TYPES.map((t) => (
            <button
              key={t || "all"}
              onClick={() => setSubjectType(t)}
              className={cn(
                "text-[10px] px-2 py-1 rounded-md border capitalize transition-colors",
                subjectType === t
                  ? "border-cyan-500/30 bg-cyan-500/10 text-cyan-300"
                  : "border-white/5 text-slate-500 hover:text-slate-300",
              )}
            >
              {t ? t.replace(/_/g, " ") : "All"}
            </button>
          ))}
        </div>
      </div>

      {q.isLoading ? (
        <div className="flex items-center gap-2 text-slate-500 text-xs py-8 justify-center">
          <Loader2 className="w-4 h-4 animate-spin" /> Loading history…
        </div>
      ) : q.isError ? (
        <div className="text-xs text-rose-400 py-8 text-center">Could not load the change log.</div>
      ) : entries.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-white/5 p-12 text-center text-slate-600">
          <ScrollText className="w-8 h-8 mx-auto mb-3 opacity-20" />
          <p className="text-xs">
            No canonical changes recorded yet. As you play and the GM canonizes facts,
            every committed change appears here.
          </p>
        </div>
      ) : (
        <div className="glass rounded-2xl border border-white/5 divide-y divide-white/5">
          {entries.map((e) => (
            <EntryRow key={e.change_id} entry={e} />
          ))}
        </div>
      )}
    </div>
  );
}
