"use client";

import Link from "next/link";
import { History, Play } from "lucide-react";
import type { Session } from "@/lib/types";
import { formatRelativeTime } from "@/lib/utils";

/** Last-N sessions with one-click resume into the play console. */
export function ContinuePlayingRail({ sessions }: { sessions: Session[] }) {
  const recent = [...sessions]
    .sort((a, b) => (b.updated_at ?? "").localeCompare(a.updated_at ?? ""))
    .slice(0, 6);
  if (recent.length === 0) return null;

  return (
    <section aria-label="Continue playing" className="space-y-2">
      <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">
        <History className="w-3.5 h-3.5" /> Continue playing
      </div>
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-3">
        {recent.map((s) => (
          <div key={s.id} className="glass flex items-center justify-between gap-3 rounded-xl px-4 py-3">
            <div className="min-w-0">
              <div className="truncate text-sm font-medium text-slate-200">{s.title}</div>
              <div className="mt-0.5 truncate text-[11px] text-slate-500">
                {s.universe_label ?? "Unbound"} · {s.message_count} messages ·{" "}
                {formatRelativeTime(s.updated_at)}
              </div>
            </div>
            <Link
              href={`/play?session=${s.id}`}
              className="btn-cyber flex flex-shrink-0 items-center gap-1.5 px-3 py-1.5 text-xs"
            >
              <Play className="h-3 w-3" /> Continue
            </Link>
          </div>
        ))}
      </div>
    </section>
  );
}
