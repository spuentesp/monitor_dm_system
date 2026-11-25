"use client";

import { useEffect, useMemo, useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { Loader2, RefreshCw, Sparkles } from "lucide-react";
import { gmApi, storiesApi } from "@/lib/api";
import type { PlotHook } from "@/lib/types";
import { cn } from "@/lib/utils";
import { gmErrorMessage } from "@/components/gm/gmErrors";

export function PlotHooksPanel({ universeId }: { universeId: string | null }) {
  const [hooks, setHooks] = useState<PlotHook[]>([]);
  const [dismissed, setDismissed] = useState<Set<string>>(new Set());
  const [saved, setSaved] = useState<Set<string>>(new Set());
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

  const mutation = useMutation({
    mutationFn: () => gmApi.suggestHooks(universeId!, storyId || undefined),
    onSuccess: (data) => {
      setHooks(data.hooks);
      setDismissed(new Set());
      setSaved(new Set());
    },
  });

  const saveHook = useMutation({
    mutationFn: (hook: PlotHook) =>
      gmApi.saveHook({
        universe_id: universeId!,
        story_id: storyId,
        title: hook.title,
        description: hook.description,
        urgency: hook.urgency,
        potential_outcomes: hook.potential_outcomes ?? [],
        connected_threads: hook.connected_threads ?? [],
      }),
    onSuccess: (_data, hook) => {
      setSaved((prev) => new Set(prev).add(hook.hook_id ?? hook.title));
    },
  });

  if (!universeId) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-center space-y-2 px-4">
        <Sparkles className="w-8 h-8 text-slate-700" />
        <p className="text-xs text-slate-600">Select a universe to generate plot hooks</p>
      </div>
    );
  }

  const visibleHooks = hooks.filter((hook) => !dismissed.has(hook.hook_id ?? hook.title));

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <div className="flex items-center gap-2 px-4 py-3 border-b border-white/5 flex-shrink-0">
        <Sparkles className="w-3.5 h-3.5 text-amber-400" />
        <span className="text-xs font-semibold text-slate-300 flex-1">Plot Hooks</span>
        <select
          value={storyId}
          onChange={(e) => setStoryId(e.target.value)}
          className="input-cyber py-1 text-xs max-w-[150px]"
          disabled={stories.length === 0}
        >
          <option value="">Select story</option>
          {stories.map((s) => (
            <option key={s.id} value={s.id}>{s.title}</option>
          ))}
        </select>
        <button
          onClick={() => mutation.mutate()}
          disabled={mutation.isPending}
          className="btn-cyber text-xs py-1 px-3 max-xl:min-h-11"
        >
          {mutation.isPending ? <Loader2 className="w-3 h-3 animate-spin" /> : <RefreshCw className="w-3 h-3" />}
          Generate
        </button>
      </div>
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
        {mutation.isPending && hooks.length === 0 && (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="w-5 h-5 text-slate-600 animate-spin" />
          </div>
        )}
        {mutation.isError && (
          <div className="text-xs text-red-400 text-center py-4">
            {gmErrorMessage(mutation.error, "Failed to generate hooks. Try again.")}
          </div>
        )}
        {visibleHooks.map((hook) => {
          const hookKey = hook.hook_id ?? hook.title;
          return (
            <div key={hookKey} className="glass-dark rounded-xl border border-white/5 p-3 space-y-1.5">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-slate-200">{hook.title}</span>
                <span className={cn(
                  "text-[10px] px-1.5 py-0.5 rounded font-medium",
                  hook.urgency === "critical" ? "bg-red-500/15 text-red-400" :
                  hook.urgency === "high" ? "bg-amber-500/15 text-amber-400" :
                  hook.urgency === "medium" ? "bg-cyan-500/15 text-cyan-400" :
                  "bg-slate-500/15 text-slate-400"
                )}>
                  {hook.urgency}
                </span>
              </div>
              <p className="text-xs text-slate-400 leading-relaxed">{hook.description}</p>
              {hook.potential_outcomes && hook.potential_outcomes.length > 0 && (
                <p className="text-[10px] text-slate-500">Outcomes: {hook.potential_outcomes.join(" · ")}</p>
              )}
              {hook.connected_entities.length > 0 && (
                <div className="flex flex-wrap gap-1 mt-1">
                  {hook.connected_entities.map((e, j) => (
                    <span key={j} className="text-[10px] bg-white/5 px-1.5 py-0.5 rounded text-slate-500">{e}</span>
                  ))}
                </div>
              )}
              <div className="text-[10px] text-slate-600">
                Suggested scene: <span className="text-slate-400">{hook.suggested_scene_type}</span>
              </div>
              <div className="flex gap-1 pt-1">
                <button
                  type="button"
                  onClick={() => {
                    const title = window.prompt("Hook title", hook.title);
                    if (title === null) return;
                    const description = window.prompt("Hook description", hook.description);
                    if (description === null) return;
                    setHooks((prev) => prev.map((h) => h.hook_id === hook.hook_id ? { ...h, title, description } : h));
                  }}
                  className="text-[10px] px-2 py-0.5 rounded border border-white/10 text-slate-300 hover:bg-white/5"
                >
                  Edit
                </button>
                <button
                  type="button"
                  onClick={() => setDismissed((prev) => new Set(prev).add(hookKey))}
                  className="text-[10px] px-2 py-0.5 rounded border border-red-500/25 text-red-300 hover:bg-red-500/10"
                >
                  Dismiss
                </button>
                <button
                  type="button"
                  onClick={() => saveHook.mutate(hook)}
                  disabled={!storyId || saveHook.isPending || saved.has(hookKey)}
                  className="text-[10px] px-2 py-0.5 rounded border border-cyan-500/25 text-cyan-300 hover:bg-cyan-500/10 disabled:opacity-50"
                >
                  {saved.has(hookKey) ? "Saved" : "Save as thread"}
                </button>
              </div>
            </div>
          );
        })}
        {!mutation.isPending && hooks.length === 0 && (
          <div className="text-center py-8">
            <Sparkles className="w-8 h-8 text-slate-700 mx-auto mb-2" />
            <p className="text-xs text-slate-600">Click Generate to discover plot hooks</p>
          </div>
        )}
      </div>
    </div>
  );
}
