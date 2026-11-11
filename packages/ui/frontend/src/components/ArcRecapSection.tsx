"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BookOpen, ChevronDown, ChevronRight, Loader2, RefreshCw, Sparkles } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { ApiError, storiesApi } from "@/lib/api";
import type { ArcRecap, ArcRecapDetail } from "@/lib/types";
import { cn, formatRelativeTime } from "@/lib/utils";

const DETAIL_LEVELS: ArcRecapDetail[] = ["short", "standard", "detailed"];

/**
 * CF-12 — "Campaign so far": the persisted story-arc recap for one story.
 * Reads never regenerate (GET returns the persisted artifact, 404 = none yet);
 * the refresh button POSTs a regeneration with a chosen length. Used on the
 * story detail (worlds tree) and as a collapsible in the CF-7 prep panel.
 */
export function ArcRecapSection({
  storyId,
  collapsible = false,
  defaultOpen = true,
}: {
  storyId: string | null;
  collapsible?: boolean;
  defaultOpen?: boolean;
}) {
  const qc = useQueryClient();
  const [detail, setDetail] = useState<ArcRecapDetail>("standard");
  const [open, setOpen] = useState(defaultOpen);

  const recapQuery = useQuery({
    queryKey: ["arc-recap", storyId],
    queryFn: async (): Promise<ArcRecap | null> => {
      try {
        return await storiesApi.getArcRecap(storyId!);
      } catch (e) {
        if (e instanceof ApiError && e.status === 404) return null; // none generated yet
        throw e;
      }
    },
    enabled: !!storyId,
    staleTime: 30_000,
    retry: 1,
  });

  const refresh = useMutation({
    mutationFn: (d: ArcRecapDetail) => storiesApi.refreshArcRecap(storyId!, d),
    onSuccess: (data) => {
      qc.setQueryData(["arc-recap", storyId], data);
      setOpen(true);
    },
  });

  if (!storyId) return null;

  const recap = recapQuery.data ?? null;
  const busy = refresh.isPending || (recapQuery.isFetching && !recap);

  const header = (
    <div className="flex items-center gap-2">
      <BookOpen className="w-3 h-3 text-purple-400" />
      <h3 className="text-[10px] font-bold tracking-widest uppercase text-slate-500 flex-1">
        Campaign so far
      </h3>
      {collapsible && (
        <span className="text-slate-600">
          {open ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
        </span>
      )}
      {recap && (
        <span
          data-testid="arc-recap-persisted-badge"
          className="text-[9px] px-1.5 py-px rounded-full border border-emerald-500/30 bg-emerald-500/10 text-emerald-300"
          title={`Persisted recap over ${recap.scene_count} scene(s), generated ${recap.generated_at}`}
        >
          persisted · {recap.scene_count} scenes · {formatRelativeTime(recap.generated_at)}
        </span>
      )}
    </div>
  );

  return (
    <section data-testid="arc-recap-section" className="space-y-1.5">
      {collapsible ? (
        <button
          type="button"
          data-testid="arc-recap-toggle"
          onClick={() => setOpen((o) => !o)}
          className="w-full text-left flex items-center gap-2 hover:bg-white/5 rounded-lg px-1 py-0.5"
          aria-expanded={open}
        >
          {header}
        </button>
      ) : (
        header
      )}

      {(!collapsible || open) && (
        <div className="glass-dark rounded-lg border border-white/5 p-2.5 space-y-2">
          {recapQuery.isLoading ? (
            <div className="flex items-center gap-2 py-2 text-slate-600 text-xs">
              <Loader2 className="w-3.5 h-3.5 animate-spin" /> Loading campaign recap…
            </div>
          ) : recapQuery.isError ? (
            <div className="space-y-1.5">
              <p className="text-[10px] text-red-400">Couldn&apos;t load the campaign recap.</p>
              <button
                type="button"
                onClick={() => recapQuery.refetch()}
                className="btn-cyber text-[10px] py-0.5 px-2"
              >
                Retry
              </button>
            </div>
          ) : recap ? (
            <>
              <div
                data-testid="arc-recap-body"
                className="prose prose-invert prose-sm max-w-none text-xs text-slate-300 leading-relaxed [&_h1]:text-sm [&_h2]:text-xs [&_h2]:text-purple-300 [&_h3]:text-[11px] [&_p]:my-1 [&_ul]:my-1 [&_li]:my-0"
              >
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{recap.recap}</ReactMarkdown>
              </div>
              <div className="flex items-center gap-2 pt-1 border-t border-white/5">
                <label className="text-[9px] uppercase tracking-wider text-slate-600" htmlFor={`arc-detail-${storyId}`}>
                  Length
                </label>
                <select
                  id={`arc-detail-${storyId}`}
                  data-testid="arc-recap-detail"
                  value={detail}
                  onChange={(e) => setDetail(e.target.value as ArcRecapDetail)}
                  className="input-cyber py-0.5 text-[10px]"
                  disabled={refresh.isPending}
                >
                  {DETAIL_LEVELS.map((d) => (
                    <option key={d} value={d}>{d}</option>
                  ))}
                </select>
                <button
                  type="button"
                  data-testid="arc-recap-refresh"
                  onClick={() => refresh.mutate(detail)}
                  disabled={refresh.isPending}
                  className={cn("btn-cyber text-[10px] py-0.5 px-2 ml-auto", refresh.isPending && "opacity-40 cursor-not-allowed")}
                >
                  {refresh.isPending ? (
                    <Loader2 className="w-3 h-3 animate-spin" />
                  ) : (
                    <RefreshCw className="w-3 h-3" />
                  )}
                  Refresh recap
                </button>
              </div>
              {refresh.isError && (
                <p className="text-[10px] text-red-400">Refresh failed — the persisted recap is still shown.</p>
              )}
            </>
          ) : (
            <div className="space-y-1.5">
              <p className="text-[11px] text-slate-600 italic">
                No campaign recap yet — generate one to see where the story stands.
              </p>
              <button
                type="button"
                data-testid="arc-recap-generate"
                onClick={() => refresh.mutate(detail)}
                disabled={refresh.isPending}
                className={cn("btn-cyber text-[10px] py-1 px-2", refresh.isPending && "opacity-40 cursor-not-allowed")}
              >
                {refresh.isPending ? (
                  <Loader2 className="w-3 h-3 animate-spin" />
                ) : (
                  <Sparkles className="w-3 h-3" />
                )}
                Generate campaign recap
              </button>
              {refresh.isError && (
                <p className="text-[10px] text-red-400">Generation failed — try again.</p>
              )}
            </div>
          )}
          {busy && !recapQuery.isLoading && (
            <p className="text-[9px] text-slate-600">Refreshing in the background…</p>
          )}
        </div>
      )}
    </section>
  );
}
