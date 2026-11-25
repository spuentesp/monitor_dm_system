"use client";

import { useEffect, useMemo, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { GitBranch, Loader2 } from "lucide-react";
import { storiesApi } from "@/lib/api";
import type { StoryThread } from "@/lib/types";
import { cn } from "@/lib/utils";

const THREAD_URGENCY_TAG: Record<string, string> = {
  immediate: "bg-red-500/15 text-red-400",
  high: "bg-amber-500/15 text-amber-400",
  medium: "bg-cyan-500/15 text-cyan-400",
  low: "bg-slate-500/15 text-slate-400",
};

export function ThreadsPanel({ universeId }: { universeId: string | null }) {
  const qc = useQueryClient();
  const [storyId, setStoryId] = useState("");

  const { data: storiesData } = useQuery({
    queryKey: ["universe-stories", universeId],
    queryFn: () => storiesApi.listStories({ universe_id: universeId!, limit: 100 }),
    enabled: !!universeId,
    staleTime: 15_000,
  });
  const stories = useMemo(() => storiesData?.stories ?? [], [storiesData]);

  useEffect(() => {
    if (!storyId && stories.length > 0) setStoryId(stories[0].id);
    if (storyId && stories.length > 0 && !stories.some((s) => s.id === storyId)) {
      setStoryId(stories[0].id);
    }
  }, [stories, storyId]);

  const { data: threads = [], isLoading } = useQuery({
    queryKey: ["story-threads", storyId],
    queryFn: () => storiesApi.listThreads(storyId),
    enabled: !!storyId,
    staleTime: 30_000,
    retry: 1,
  });

  const updateThread = useMutation({
    mutationFn: ({
      threadId,
      action,
      note,
    }: {
      threadId: string;
      action: "resolve" | "dismiss" | "note";
      note?: string;
    }) => storiesApi.updateThread(storyId, threadId, action, note),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["story-threads", storyId] }),
  });

  if (!universeId) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-center space-y-2 px-4">
        <GitBranch className="w-8 h-8 text-slate-700" />
        <p className="text-xs text-slate-600">Select a universe to track unresolved threads</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <div className="flex items-center gap-2 px-4 py-3 border-b border-white/5 flex-shrink-0">
        <GitBranch className="w-3.5 h-3.5 text-purple-400" />
        <span className="text-xs font-semibold text-slate-300 flex-1">Unresolved Threads</span>
        <select
          value={storyId}
          onChange={(e) => setStoryId(e.target.value)}
          className="input-cyber py-1 text-xs max-w-[170px]"
          disabled={stories.length === 0}
        >
          {stories.length === 0 && <option value="">No stories yet</option>}
          {stories.map((s) => (
            <option key={s.id} value={s.id}>
              {s.title} ({s.status})
            </option>
          ))}
        </select>
      </div>
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-2">
        {isLoading && (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="w-5 h-5 text-slate-600 animate-spin" />
          </div>
        )}
        {!isLoading && threads.length === 0 && (
          <div className="text-center py-8">
            <GitBranch className="w-8 h-8 text-slate-700 mx-auto mb-2" />
            <p className="text-xs text-slate-600">
              {storyId ? "No open threads in this story" : "Pick a story to see its loose ends"}
            </p>
          </div>
        )}
        {threads.map((t: StoryThread, i) => (
          <div key={t.id ?? `${t.title}-${i}`} data-gm-entry className="glass-dark rounded-xl border border-white/5 p-3 space-y-1.5">
            <div className="flex items-center justify-between gap-2">
              <span className="text-xs font-medium text-slate-200 leading-snug">{t.title}</span>
              {t.urgency && (
                <span className={cn("text-[10px] px-1.5 py-0.5 rounded font-medium flex-shrink-0", THREAD_URGENCY_TAG[t.urgency] ?? THREAD_URGENCY_TAG.low)}>
                  {t.urgency}
                </span>
              )}
            </div>
            <div className="flex items-center gap-2 text-[10px] text-slate-600">
              {t.thread_type && <span className="capitalize">{t.thread_type.replace(/_/g, " ")}</span>}
              <span className="capitalize">{t.status.replace(/_/g, " ")}</span>
              {t.source === "checkpoint" && <span className="italic">from story state</span>}
            </div>
            {t.gm_notes && <p className="text-[10px] text-slate-500">{t.gm_notes}</p>}
            {t.id && (
              <div className="flex gap-1 pt-1">
                <button
                  type="button"
                  onClick={() => updateThread.mutate({ threadId: t.id!, action: "resolve" })}
                  className="text-[10px] px-2 py-0.5 rounded border border-emerald-500/25 text-emerald-300 hover:bg-emerald-500/10"
                >
                  Resolve
                </button>
                <button
                  type="button"
                  onClick={() => updateThread.mutate({ threadId: t.id!, action: "dismiss" })}
                  className="text-[10px] px-2 py-0.5 rounded border border-red-500/25 text-red-300 hover:bg-red-500/10"
                >
                  Dismiss
                </button>
                <button
                  type="button"
                  onClick={() => {
                    const note = window.prompt("GM note for this thread", t.gm_notes ?? "");
                    if (note !== null) updateThread.mutate({ threadId: t.id!, action: "note", note });
                  }}
                  className="text-[10px] px-2 py-0.5 rounded border border-white/10 text-slate-300 hover:bg-white/5"
                >
                  Note
                </button>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
