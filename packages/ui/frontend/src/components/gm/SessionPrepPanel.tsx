"use client";

import { useEffect, useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { ClipboardList, Loader2, Sparkles } from "lucide-react";
import { gmApi, storiesApi } from "@/lib/api";
import type { SessionPrep, PrepItem } from "@/lib/types";
import { cn } from "@/lib/utils";
import { gmErrorMessage } from "@/components/gm/gmErrors";
import { DifficultyBadge } from "@/components/gm/DifficultyBadge";

export function SessionPrepPanel({ universeId }: { universeId: string | null }) {
  const [prep, setPrep] = useState<SessionPrep | null>(null);
  const [checklist, setChecklist] = useState<PrepItem[]>([]);
  const [storyId, setStoryId] = useState("");

  const { data: storiesData } = useQuery({
    queryKey: ["universe-stories", universeId],
    queryFn: () => storiesApi.listStories({ universe_id: universeId!, limit: 100 }),
    enabled: !!universeId,
    staleTime: 15_000,
  });
  const stories = storiesData?.stories ?? [];

  // Default to the most recent story once loaded
  useEffect(() => {
    if (!storyId && stories.length > 0) setStoryId(stories[0].id);
    if (storyId && stories.length > 0 && !stories.some((s) => s.id === storyId)) {
      setStoryId(stories[0].id);
    }
  }, [stories, storyId]);

  const mutation = useMutation({
    mutationFn: () => gmApi.generateSessionPrep(universeId!, storyId),
    onSuccess: (data) => {
      setPrep(data.prep);
      setChecklist(data.prep.checklist ?? []);
    },
  });

  const generateItem = useMutation({
    mutationFn: (item: PrepItem) =>
      gmApi.generatePrepItem({
        universe_id: universeId!,
        story_id: storyId,
        category: item.category,
        description: item.description,
      }),
    onSuccess: (data, item) => {
      setChecklist((prev) =>
        prev.map((candidate) =>
          candidate.item_id === item.item_id
            ? { ...candidate, generated_content: data.content }
            : candidate,
        ),
      );
    },
  });

  if (!universeId) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-center space-y-2 px-4">
        <ClipboardList className="w-8 h-8 text-slate-700" />
        <p className="text-xs text-slate-600">Select a universe to generate session prep</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <div className="flex items-center gap-2 px-4 py-3 border-b border-white/5 flex-shrink-0">
        <ClipboardList className="w-3.5 h-3.5 text-emerald-400" />
        <span className="text-xs font-semibold text-slate-300 flex-1">Session Prep</span>
        <select
          value={storyId}
          onChange={(e) => setStoryId(e.target.value)}
          className="input-cyber py-1 text-xs max-w-[170px]"
          disabled={stories.length === 0}
          title="Which story to prep for"
        >
          {stories.length === 0 && <option value="">No stories yet</option>}
          {stories.map((s) => (
            <option key={s.id} value={s.id}>
              {s.title} ({s.status})
            </option>
          ))}
        </select>
        <button
          onClick={() => mutation.mutate()}
          disabled={mutation.isPending || !storyId}
          className={cn("btn-cyber text-xs py-1 px-3 max-xl:min-h-11", !storyId && "opacity-40 cursor-not-allowed")}
        >
          {mutation.isPending ? <Loader2 className="w-3 h-3 animate-spin" /> : <Sparkles className="w-3 h-3" />}
          Generate
        </button>
      </div>
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-4">
        {mutation.isPending && !prep && (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="w-5 h-5 text-slate-600 animate-spin" />
          </div>
        )}
        {mutation.isError && (
          <div className="text-xs text-red-400 text-center py-4">
            {gmErrorMessage(mutation.error, "Failed to generate session prep. Try again.")}
          </div>
        )}
        {prep && (
          <>
            {/* Recap */}
            <section className="space-y-1.5">
              <h3 className="text-[10px] font-bold tracking-widest uppercase text-emerald-400">Recap</h3>
              <p className="text-xs text-slate-300 leading-relaxed glass-dark rounded-xl border border-white/5 p-3">
                {prep.recap}
              </p>
            </section>

            {/* Encounter difficulty (CF-13) — the label and the arithmetic. */}
            {prep.encounter_difficulty && (
              <section className="space-y-1.5">
                <h3 className="text-[10px] font-bold tracking-widest uppercase text-red-400">
                  Encounter Difficulty
                </h3>
                <DifficultyBadge difficulty={prep.encounter_difficulty} />
              </section>
            )}

            {/* Open Threads */}
            {prep.open_threads.length > 0 && (
              <section className="space-y-1.5">
                <h3 className="text-[10px] font-bold tracking-widest uppercase text-amber-400">Open Threads</h3>
                <ul className="space-y-1">
                  {prep.open_threads.map((t, i) => (
                    <li key={i} className="text-xs text-slate-400 flex items-start gap-1.5">
                      <span className="text-amber-500 mt-0.5">•</span> {t}
                    </li>
                  ))}
                </ul>
              </section>
            )}

            {/* Hooks */}
            {prep.hooks.length > 0 && (
              <section className="space-y-1.5">
                <h3 className="text-[10px] font-bold tracking-widest uppercase text-cyan-400">Suggested Hooks</h3>
                {prep.hooks.map((h, i) => (
                  <div key={i} className="glass-dark rounded-lg border border-white/5 p-2.5">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-medium text-slate-200">{h.title}</span>
                      <span className="text-[10px] text-slate-600">{h.urgency}</span>
                    </div>
                    <p className="text-[11px] text-slate-500 mt-0.5">{h.description}</p>
                  </div>
                ))}
              </section>
            )}

            {/* NPC Reminders */}
            {prep.npc_reminders.length > 0 && (
              <section className="space-y-1.5">
                <h3 className="text-[10px] font-bold tracking-widest uppercase text-purple-400">NPC Reminders</h3>
                <div className="flex flex-wrap gap-1.5">
                  {prep.npc_reminders.map((npc, i) => (
                    <span key={i} className="text-xs bg-purple-500/10 text-purple-300 px-2 py-1 rounded-lg border border-purple-500/20">
                      {npc}
                    </span>
                  ))}
                </div>
              </section>
            )}

            {/* World State Changes */}
            {prep.world_state_changes.length > 0 && (
              <section className="space-y-1.5">
                <h3 className="text-[10px] font-bold tracking-widest uppercase text-slate-400">World Changes</h3>
                <ul className="space-y-1">
                  {prep.world_state_changes.map((c, i) => (
                    <li key={i} className="text-xs text-slate-500 flex items-start gap-1.5">
                      <span className="text-slate-600 mt-0.5">•</span> {c}
                    </li>
                  ))}
                </ul>
              </section>
            )}

            {/* Prep Checklist */}
            {checklist.length > 0 && (
              <section className="space-y-1.5">
                <h3 className="text-[10px] font-bold tracking-widest uppercase text-cyan-400">Prep Checklist</h3>
                <div className="space-y-2">
                  {checklist.map((item) => (
                    <div key={item.item_id} className="glass-dark rounded-lg border border-white/5 p-2.5 space-y-1">
                      <div className="flex items-center justify-between gap-2">
                        <div className="min-w-0">
                          <span className="text-[9px] uppercase tracking-wider text-slate-500">{item.category}</span>
                          <p className="text-xs text-slate-300">{item.description}</p>
                        </div>
                        <span className={cn(
                          "text-[9px] px-1.5 py-0.5 rounded border",
                          item.status === "ready" ? "border-emerald-500/25 text-emerald-300" :
                          item.status === "skipped" ? "border-slate-500/20 text-slate-500" :
                          "border-amber-500/20 text-amber-300",
                        )}>
                          {item.status}
                        </span>
                      </div>
                      {item.generated_content && (
                        <p className="text-[11px] text-slate-400">{item.generated_content}</p>
                      )}
                      <div className="flex gap-1">
                        <button
                          type="button"
                          onClick={() => setChecklist((prev) => prev.map((candidate) => candidate.item_id === item.item_id ? { ...candidate, status: "ready" } : candidate))}
                          className="text-[9px] px-2 py-0.5 rounded border border-emerald-500/20 text-emerald-300 hover:bg-emerald-500/10"
                        >
                          Ready
                        </button>
                        <button
                          type="button"
                          onClick={() => setChecklist((prev) => prev.map((candidate) => candidate.item_id === item.item_id ? { ...candidate, status: "skipped" } : candidate))}
                          className="text-[9px] px-2 py-0.5 rounded border border-white/10 text-slate-400 hover:bg-white/5"
                        >
                          Skip
                        </button>
                        <button
                          type="button"
                          onClick={() => generateItem.mutate(item)}
                          disabled={generateItem.isPending}
                          className="text-[9px] px-2 py-0.5 rounded border border-cyan-500/20 text-cyan-300 hover:bg-cyan-500/10 disabled:opacity-50"
                        >
                          Generate
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </section>
            )}
          </>
        )}
        {!mutation.isPending && !prep && (
          <div className="text-center py-8">
            <ClipboardList className="w-8 h-8 text-slate-700 mx-auto mb-2" />
            <p className="text-xs text-slate-600">Pick a story and click Generate</p>
          </div>
        )}
      </div>
    </div>
  );
}
