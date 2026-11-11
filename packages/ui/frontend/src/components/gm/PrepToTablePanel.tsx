"use client";

import { useEffect, useState } from "react";
import { ClipboardList, Loader2, NotebookPen, Sparkles, Users } from "lucide-react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { gmApi, storiesApi } from "@/lib/api";
import { gmTableApi } from "@/lib/gm-table-api";
import type {
  GmPrepBundle,
  PrepExtraction,
  PrepLocationItem,
  PrepNpcItem,
  PrepThreadItem,
} from "@/lib/gm-table-types";
import { cn } from "@/lib/utils";
import { ArcRecapSection } from "@/components/ArcRecapSection";

type ReviewNpc = PrepNpcItem & { included: boolean };
type ReviewLocation = PrepLocationItem & { included: boolean };
type ReviewThread = PrepThreadItem & { included: boolean };

/**
 * Prep to table (Phase 7 Part B, CF-7): one flow —
 * ingest the GM's notes, review what was extracted, and open the /gm page
 * with tonight's NPCs, locations and threads ready.
 */
export function PrepToTablePanel({ universeId }: { universeId: string | null }) {
  const [notes, setNotes] = useState("");
  const [storyId, setStoryId] = useState("");
  const [npcs, setNpcs] = useState<ReviewNpc[]>([]);
  const [locations, setLocations] = useState<ReviewLocation[]>([]);
  const [threads, setThreads] = useState<ReviewThread[]>([]);
  const [notesSummary, setNotesSummary] = useState("");
  const [tonight, setTonight] = useState<GmPrepBundle | null>(null);
  const [savedInfo, setSavedInfo] = useState<string | null>(null);
  const [stagingErrors, setStagingErrors] = useState<string[]>([]);

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

  const { data: scratchNotes } = useQuery({
    queryKey: ["gm-notes", universeId],
    queryFn: () => gmApi.getNotes(universeId!),
    enabled: !!universeId,
    staleTime: 30_000,
  });

  const savedPrep = useQuery({
    queryKey: ["gm-prep", universeId, storyId],
    queryFn: () => gmTableApi.getPrep(universeId!, storyId || null),
    enabled: !!universeId,
    staleTime: 15_000,
  });
  useEffect(() => {
    if (savedPrep.data?.found && savedPrep.data.bundle) setTonight(savedPrep.data.bundle);
  }, [savedPrep.data]);

  const extract = useMutation({
    mutationFn: () => gmTableApi.extractPrep(universeId!, notes, storyId || null),
    onSuccess: (data: PrepExtraction) => {
      setNpcs(data.npcs.map((n) => ({ ...n, included: true })));
      setLocations(data.locations.map((l) => ({ ...l, included: true })));
      setThreads(data.threads.map((t) => ({ ...t, included: true })));
      setNotesSummary(data.notes_summary);
      setSavedInfo(null);
      setStagingErrors([]);
    },
  });

  const commit = useMutation({
    mutationFn: () =>
      gmTableApi.commitPrep({
        universe_id: universeId!,
        story_id: storyId,
        npcs: npcs.filter((n) => n.included).map(({ included: _i, ...n }) => n),
        locations: locations.filter((l) => l.included).map(({ included: _i, ...l }) => l),
        threads: threads.filter((t) => t.included).map(({ included: _i, ...t }) => t),
      }),
    onSuccess: (data) => {
      setTonight(data.bundle);
      setStagingErrors(data.staging_errors ?? []);
      setSavedInfo(
        `Saved ${data.committed_thread_ids.length} thread(s); ` +
          `${data.staged_proposal_ids.length} new NPC/location proposal(s) staged for review.`,
      );
    },
  });

  if (!universeId) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-center space-y-2 px-4">
        <ClipboardList className="w-8 h-8 text-slate-700" />
        <p className="text-xs text-slate-600">Select a universe to prep tonight&apos;s session</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <div className="flex items-center gap-2 px-4 py-3 border-b border-white/5 flex-shrink-0">
        <ClipboardList className="w-3.5 h-3.5 text-emerald-400" />
        <span className="text-xs font-semibold text-slate-300 flex-1">Prep to Table</span>
        <select
          value={storyId}
          onChange={(e) => setStoryId(e.target.value)}
          className="input-cyber py-1 text-xs max-w-[150px]"
          disabled={stories.length === 0}
          title="Which story tonight's prep is for"
        >
          {stories.length === 0 && <option value="">No stories yet</option>}
          {stories.map((s) => (
            <option key={s.id} value={s.id}>{s.title}</option>
          ))}
        </select>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-4">
        {/* CF-12 — "campaign so far" collapsible for the selected story */}
        <ArcRecapSection storyId={storyId || null} collapsible defaultOpen={false} />

        {/* Notes */}
        <section className="space-y-1.5">
          <div className="flex items-center gap-2">
            <NotebookPen className="w-3 h-3 text-slate-500" />
            <h3 className="text-[10px] font-bold tracking-widest uppercase text-slate-500 flex-1">
              Tonight&apos;s notes
            </h3>
            {scratchNotes?.content && scratchNotes.content !== notes && (
              <button
                type="button"
                onClick={() => setNotes(scratchNotes.content)}
                className="text-[10px] px-2 py-0.5 rounded border border-white/10 text-slate-300 hover:bg-white/5"
              >
                Use notebook notes
              </button>
            )}
          </div>
          <textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder={"Paste or type what you have planned for tonight…\n- The party returns to Ironwatch at dusk\n- Mira wants the key back\n- The Merchants' Guild makes its move"}
            className="input-cyber w-full h-28 resize-none text-xs font-mono leading-relaxed"
            spellCheck={false}
          />
          <button
            type="button"
            onClick={() => extract.mutate()}
            disabled={!notes.trim() || extract.isPending}
            className={cn("btn-cyber text-xs py-1 px-3", !notes.trim() && "opacity-40 cursor-not-allowed")}
          >
            {extract.isPending ? <Loader2 className="w-3 h-3 animate-spin" /> : <Sparkles className="w-3 h-3" />}
            Extract for review
          </button>
          {extract.isError && (
            <p className="text-[10px] text-red-400">Extraction failed — try again.</p>
          )}
        </section>

        {/* Review */}
        {(npcs.length > 0 || locations.length > 0 || threads.length > 0) && (
          <section className="space-y-2">
            <h3 className="text-[10px] font-bold tracking-widest uppercase text-amber-400">
              Review what was extracted
            </h3>
            {notesSummary && <p className="text-[10px] text-slate-500">{notesSummary}</p>}

            {npcs.map((npc, i) => (
              <div key={`npc-${i}`} className="glass-dark rounded-lg border border-white/5 p-2 space-y-1">
                <label className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={npc.included}
                    onChange={(e) =>
                      setNpcs((prev) => prev.map((n, j) => (j === i ? { ...n, included: e.target.checked } : n)))
                    }
                    className="h-3 w-3 accent-emerald-400"
                  />
                  <span className="text-[9px] uppercase tracking-wider text-purple-300">NPC</span>
                  {npc.existing_entity_id && (
                    <span className="text-[9px] text-emerald-400">already in canon</span>
                  )}
                </label>
                <input
                  value={npc.name}
                  onChange={(e) => setNpcs((prev) => prev.map((n, j) => (j === i ? { ...n, name: e.target.value } : n)))}
                  className="input-cyber w-full py-0.5 text-xs"
                />
                <input
                  value={npc.want}
                  placeholder="What they want tonight"
                  onChange={(e) => setNpcs((prev) => prev.map((n, j) => (j === i ? { ...n, want: e.target.value } : n)))}
                  className="input-cyber w-full py-0.5 text-[10px]"
                />
              </div>
            ))}

            {locations.map((loc, i) => (
              <div key={`loc-${i}`} className="glass-dark rounded-lg border border-white/5 p-2 space-y-1">
                <label className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={loc.included}
                    onChange={(e) =>
                      setLocations((prev) => prev.map((l, j) => (j === i ? { ...l, included: e.target.checked } : l)))
                    }
                    className="h-3 w-3 accent-emerald-400"
                  />
                  <span className="text-[9px] uppercase tracking-wider text-cyan-300">Location</span>
                  {loc.existing_entity_id && (
                    <span className="text-[9px] text-emerald-400">already in canon</span>
                  )}
                </label>
                <input
                  value={loc.name}
                  onChange={(e) =>
                    setLocations((prev) => prev.map((l, j) => (j === i ? { ...l, name: e.target.value } : l)))
                  }
                  className="input-cyber w-full py-0.5 text-xs"
                />
              </div>
            ))}

            {threads.map((t, i) => (
              <div key={`thread-${i}`} className="glass-dark rounded-lg border border-white/5 p-2 space-y-1">
                <label className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={t.included}
                    onChange={(e) =>
                      setThreads((prev) => prev.map((th, j) => (j === i ? { ...th, included: e.target.checked } : th)))
                    }
                    className="h-3 w-3 accent-emerald-400"
                  />
                  <span className="text-[9px] uppercase tracking-wider text-amber-300">Thread</span>
                  <span className="text-[9px] text-slate-600">{t.urgency}</span>
                </label>
                <input
                  value={t.title}
                  onChange={(e) =>
                    setThreads((prev) => prev.map((th, j) => (j === i ? { ...th, title: e.target.value } : th)))
                  }
                  className="input-cyber w-full py-0.5 text-xs"
                />
              </div>
            ))}

            <button
              type="button"
              onClick={() => commit.mutate()}
              disabled={!storyId || commit.isPending}
              className={cn("btn-cyber text-xs py-1 px-3", !storyId && "opacity-40 cursor-not-allowed")}
              title={storyId ? "Save tonight's prep" : "Pick a story first"}
            >
              {commit.isPending ? <Loader2 className="w-3 h-3 animate-spin" /> : <Users className="w-3 h-3" />}
              Save as tonight&apos;s prep
            </button>
            {commit.isError && (
              <p className="text-[10px] text-red-400">Saving failed — nothing was lost, try again.</p>
            )}
            {savedInfo && <p className="text-[10px] text-emerald-400">{savedInfo}</p>}
            {stagingErrors.map((e, i) => (
              <p key={i} className="text-[10px] text-red-400">
                Not staged: {e}
              </p>
            ))}
          </section>
        )}

        {/* Tonight */}
        {tonight && (
          <section className="space-y-1.5">
            <h3 className="text-[10px] font-bold tracking-widest uppercase text-emerald-400">
              Tonight&apos;s table
            </h3>
            {tonight.npcs.length === 0 && tonight.locations.length === 0 && tonight.threads.length === 0 && (
              <p className="text-[10px] text-slate-600">Nothing saved for tonight yet.</p>
            )}
            {tonight.npcs.map((npc, i) => (
              <div key={`t-npc-${i}`} className="text-xs text-slate-300 bg-purple-500/10 border border-purple-500/20 rounded-lg px-2 py-1">
                <span className="font-medium">{npc.name}</span>
                {npc.want && <span className="text-[10px] text-slate-500"> — wants {npc.want}</span>}
              </div>
            ))}
            {tonight.locations.map((loc, i) => (
              <div key={`t-loc-${i}`} className="text-xs text-slate-300 bg-cyan-500/10 border border-cyan-500/20 rounded-lg px-2 py-1">
                {loc.name}
              </div>
            ))}
            {tonight.threads.map((t, i) => (
              <div key={`t-thread-${i}`} className="text-xs text-slate-300 bg-amber-500/10 border border-amber-500/20 rounded-lg px-2 py-1">
                <span className="font-medium">{t.title}</span>
                {t.thread_id && <span className="text-[9px] text-emerald-400 ml-1">saved as thread</span>}
              </div>
            ))}
          </section>
        )}
      </div>
    </div>
  );
}
