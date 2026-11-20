"use client";

import { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { AlertTriangle, Loader2, RefreshCw } from "lucide-react";
import { gmApi, storiesApi } from "@/lib/api";
import type { Contradiction } from "@/lib/types";
import { cn } from "@/lib/utils";

export function ContradictionsPanel({ universeId }: { universeId: string | null }) {
  const [contradictions, setContradictions] = useState<Contradiction[]>([]);
  const [scope, setScope] = useState<"universe" | "story" | "scene">("universe");
  const [storyId, setStoryId] = useState("");
  const [sceneId, setSceneId] = useState("");
  const [resolution, setResolution] = useState<
    "retcon_older" | "retcon_newer" | "apparent_contradiction" | "explanation_fact"
  >("explanation_fact");

  const { data: storiesData } = useQuery({
    queryKey: ["universe-stories", universeId],
    queryFn: () => storiesApi.listStories({ universe_id: universeId!, limit: 100 }),
    enabled: !!universeId && scope !== "universe",
    staleTime: 15_000,
  });
  const stories = storiesData?.stories ?? [];

  const { data: scenes = [] } = useQuery({
    queryKey: ["story-scenes", storyId],
    queryFn: () => storiesApi.listScenes(storyId),
    enabled: !!storyId && scope === "scene",
    staleTime: 15_000,
  });

  const mutation = useMutation({
    mutationFn: () =>
      gmApi.detectContradictions(universeId!, {
        scope,
        storyId: scope === "universe" ? undefined : storyId || undefined,
        sceneId: scope === "scene" ? sceneId || undefined : undefined,
      }),
    onSuccess: (data) => setContradictions(data.contradictions),
  });

  const resolveMutation = useMutation({
    mutationFn: (c: Contradiction) =>
      gmApi.resolveContradiction({
        universe_id: universeId!,
        story_id: scope === "universe" ? null : storyId || null,
        scene_id: scope === "scene" ? sceneId || null : null,
        fact_a: c.fact_a,
        fact_b: c.fact_b,
        conflict_type: c.conflict_type ?? "semantic",
        resolution,
        explanation: `${c.explanation} Resolution: ${resolution.replace(/_/g, " ")}.`,
      }),
    onSuccess: () => mutation.mutate(),
  });

  if (!universeId) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-center space-y-2 px-4">
        <AlertTriangle className="w-8 h-8 text-slate-700" />
        <p className="text-xs text-slate-600">Select a universe to detect contradictions</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <div className="flex items-center gap-2 px-4 py-3 border-b border-white/5 flex-shrink-0">
        <AlertTriangle className="w-3.5 h-3.5 text-amber-400" />
        <span className="text-xs font-semibold text-slate-300 flex-1">Contradictions</span>
        <select
          value={scope}
          onChange={(e) => {
            setScope(e.target.value as typeof scope);
            setStoryId("");
            setSceneId("");
          }}
          className="input-cyber py-1 text-xs"
        >
          <option value="universe">Universe</option>
          <option value="story">Story</option>
          <option value="scene">Scene</option>
        </select>
        {scope !== "universe" && (
          <select
            value={storyId}
            onChange={(e) => {
              setStoryId(e.target.value);
              setSceneId("");
            }}
            className="input-cyber py-1 text-xs max-w-[150px]"
          >
            <option value="">Select story</option>
            {stories.map((s) => (
              <option key={s.id} value={s.id}>{s.title}</option>
            ))}
          </select>
        )}
        {scope === "scene" && (
          <select
            value={sceneId}
            onChange={(e) => setSceneId(e.target.value)}
            className="input-cyber py-1 text-xs max-w-[150px]"
            disabled={!storyId}
          >
            <option value="">Select scene</option>
            {scenes.map((s) => (
              <option key={s.id} value={s.id}>{s.title || s.id}</option>
            ))}
          </select>
        )}
        <button
          onClick={() => mutation.mutate()}
          disabled={mutation.isPending || (scope !== "universe" && !storyId) || (scope === "scene" && !sceneId)}
          className="btn-cyber text-xs py-1 px-3 max-xl:min-h-11"
        >
          {mutation.isPending ? <Loader2 className="w-3 h-3 animate-spin" /> : <RefreshCw className="w-3 h-3" />}
          Detect
        </button>
      </div>
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
        {mutation.isPending && contradictions.length === 0 && (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="w-5 h-5 text-slate-600 animate-spin" />
          </div>
        )}
        {mutation.isError && (
          <div className="text-xs text-red-400 text-center py-4">Failed to detect contradictions. Try again.</div>
        )}
        {contradictions.map((c, i) => (
          <div key={i} className="glass-dark rounded-xl border border-white/5 p-3 space-y-2">
            <div className="flex items-center justify-between">
              <span className={cn(
                "text-[10px] px-1.5 py-0.5 rounded font-medium",
                c.severity === "high" ? "bg-red-500/15 text-red-400" :
                c.severity === "medium" ? "bg-amber-500/15 text-amber-400" :
                "bg-slate-500/15 text-slate-400"
              )}>
                {c.severity} severity
              </span>
              <span className="text-[10px] text-slate-500">{c.conflict_type ?? "semantic"}</span>
            </div>
            <div className="space-y-1">
              <div className="text-xs text-slate-300 bg-red-500/5 rounded px-2 py-1 border-l-2 border-red-500/30">
                {c.fact_a}
              </div>
              <div className="text-xs text-slate-300 bg-red-500/5 rounded px-2 py-1 border-l-2 border-red-500/30">
                {c.fact_b}
              </div>
            </div>
            <p className="text-xs text-slate-500">{c.explanation}</p>
            <p className="text-xs text-cyan-400/80">💡 {c.suggestion}</p>
            <div className="flex items-center gap-1 pt-1">
              <select
                value={resolution}
                onChange={(e) => setResolution(e.target.value as typeof resolution)}
                className="input-cyber py-1 text-xs"
              >
                <option value="retcon_older">Retcon older fact</option>
                <option value="retcon_newer">Retcon newer fact</option>
                <option value="apparent_contradiction">Mark apparent contradiction</option>
                <option value="explanation_fact">Create explanation fact</option>
              </select>
              <button
                type="button"
                onClick={() => resolveMutation.mutate(c)}
                disabled={resolveMutation.isPending}
                className="text-[10px] px-2 py-1 rounded border border-cyan-500/25 text-cyan-300 hover:bg-cyan-500/10"
              >
                Resolve
              </button>
            </div>
          </div>
        ))}
        {!mutation.isPending && contradictions.length === 0 && (
          <div className="text-center py-8">
            <AlertTriangle className="w-8 h-8 text-slate-700 mx-auto mb-2" />
            <p className="text-xs text-slate-600">Click Detect to find contradictions</p>
          </div>
        )}
      </div>
    </div>
  );
}
