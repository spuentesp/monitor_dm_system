"use client";

import Link from "next/link";
import { BookOpen, Globe2, Play } from "lucide-react";
import type { StorySummary, Universe } from "@/lib/types";
import { cn } from "@/lib/utils";

/** Playable-state badge — derived client-side until a real ingestion status exists. */
export function playableState(u: Universe): "ready" | "needs review" {
  return u.is_active ? "ready" : "needs review";
}

const BADGE_CLASSES: Record<ReturnType<typeof playableState>, string> = {
  ready: "bg-emerald-500/10 border-emerald-500/25 text-emerald-300",
  "needs review": "bg-amber-500/10 border-amber-500/25 text-amber-300",
};

export function UniverseCardGrid({
  universes,
  latestStoryByUniverse,
  storiesError = false,
}: {
  universes: Universe[];
  latestStoryByUniverse: Record<string, StorySummary | undefined>;
  /** True when the stories query failed — cards show a muted placeholder. */
  storiesError?: boolean;
}) {
  if (universes.length === 0) {
    return (
      <div className="glass rounded-xl px-6 py-10 text-center text-sm text-slate-500">
        No universes yet — author one in the{" "}
        <Link href="/forge" className="text-cyan-300 hover:underline">
          World Forge
        </Link>
        .
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
      {universes.map((u) => {
        const state = playableState(u);
        const latest = latestStoryByUniverse[u.id];
        return (
          <div key={u.id} className="glass flex flex-col gap-3 rounded-2xl p-5">
            <div className="flex items-start justify-between gap-2">
              <div className="flex items-center gap-2.5 min-w-0">
                <div className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-lg bg-cyan-500/10 border border-cyan-500/20">
                  <Globe2 className="h-4 w-4 text-cyan-400" />
                </div>
                <div className="min-w-0">
                  <div className="truncate text-sm font-semibold text-slate-100">{u.name}</div>
                  <div className="truncate text-[11px] text-slate-500">
                    {[u.genre, u.tone].filter(Boolean).join(" · ") || "—"}
                  </div>
                </div>
              </div>
              <span
                className={cn(
                  "flex-shrink-0 rounded-md border px-2 py-0.5 text-[10px] font-medium",
                  BADGE_CLASSES[state],
                )}
              >
                {state}
              </span>
            </div>

            <div className="text-[11px] text-slate-500">
              {u.entity_count} entities · {u.story_count ?? 0} stories · {u.session_count} sessions
            </div>

            <div className="flex items-center gap-1.5 text-xs text-slate-400 min-h-[1rem]">
              <BookOpen className="h-3 w-3 flex-shrink-0 text-purple-300" />
              {storiesError ? (
                <span className="truncate italic text-slate-600">Stories unavailable</span>
              ) : (
                <span className="truncate">{latest ? latest.title : "No stories yet"}</span>
              )}
            </div>

            <div className="mt-auto flex gap-2">
              <Link
                href={`/play?universe=${u.id}`}
                className="btn-cyber flex flex-1 items-center justify-center gap-1.5 px-3 py-2 text-xs"
              >
                <Play className="h-3 w-3" /> Play
              </Link>
              <Link
                href={`/forge/worlds?universe=${u.id}`}
                className="btn-ghost flex-1 px-3 py-2 text-center text-xs"
              >
                Stories
              </Link>
            </div>
          </div>
        );
      })}
    </div>
  );
}
