"use client";

import { useEffect, useMemo, useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { Check, Copy, Link2, Loader2, Scroll, Sparkles } from "lucide-react";
import { gmApi, storiesApi } from "@/lib/api";
import type { Handout, SharePublishResult } from "@/lib/types";
import { cn } from "@/lib/utils";
import { gmErrorMessage } from "@/components/gm/gmErrors";

const HANDOUT_TYPES = [
  { value: "letter", label: "Letter", icon: "✉️" },
  { value: "map_note", label: "Map Note", icon: "🗺️" },
  { value: "prophecy", label: "Prophecy", icon: "🔮" },
  { value: "journal_entry", label: "Journal", icon: "📓" },
  { value: "notice", label: "Notice", icon: "📜" },
  { value: "rumor", label: "Rumor", icon: "🗣️" },
] as const;

const HANDOUT_TONES = ["mysterious", "urgent", "warm", "ominous", "neutral"] as const;
const SPOILER_LEVELS = ["safe", "partial", "full"] as const;

export function HandoutsPanel({ universeId }: { universeId: string | null }) {
  const [handout, setHandout] = useState<Handout | null>(null);
  const [handoutType, setHandoutType] = useState<string>("letter");
  const [tone, setTone] = useState<string>("mysterious");
  const [spoilerLevel, setSpoilerLevel] = useState<string>("safe");
  // CF-14 — share links are story-scoped, so pick the story to publish into.
  const [storyId, setStoryId] = useState("");
  const [published, setPublished] = useState<SharePublishResult | null>(null);
  const [copied, setCopied] = useState(false);

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
    mutationFn: () =>
      gmApi.generateHandout(universeId!, {
        handout_type: handoutType,
        tone,
        spoiler_level: spoilerLevel,
      }),
    onSuccess: (data) => {
      setHandout(data.handout);
      // A fresh handout invalidates whatever was published before.
      setPublished(null);
    },
  });

  const publish = useMutation({
    mutationFn: () =>
      gmApi.sharePublish({
        universe_id: universeId!,
        story_id: storyId,
        artifact_type: "handout",
        title: handout!.title,
        content: handout!.content,
        spoiler_level: "party",
      }),
    onSuccess: (data) => setPublished(data),
  });
  const unpublish = useMutation({
    mutationFn: () =>
      gmApi.shareUnpublish({
        universe_id: universeId!,
        artifact_id: published!.artifact_id,
      }),
    onSuccess: () => setPublished(null),
  });
  const shareUrl = published
    ? `${typeof window !== "undefined" ? window.location.origin : ""}${published.share_path}`
    : "";

  if (!universeId) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-center space-y-2 px-4">
        <Scroll className="w-8 h-8 text-slate-700" />
        <p className="text-xs text-slate-600">Select a universe to generate handouts</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <div className="flex items-center gap-2 px-4 py-3 border-b border-white/5 flex-shrink-0">
        <Scroll className="w-3.5 h-3.5 text-amber-400" />
        <span className="text-xs font-semibold text-slate-300 flex-1">Handouts</span>
        <select
          value={storyId}
          onChange={(e) => {
            setStoryId(e.target.value);
            setPublished(null);
          }}
          className="input-cyber py-1 text-xs max-w-[150px]"
          disabled={stories.length === 0}
          aria-label="Story to publish into"
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
          {mutation.isPending ? <Loader2 className="w-3 h-3 animate-spin" /> : <Sparkles className="w-3 h-3" />}
          Generate
        </button>
      </div>

      {/* Controls */}
      <div className="px-4 py-2 space-y-2 border-b border-white/5 flex-shrink-0">
        {/* Handout type */}
        <div className="flex flex-wrap gap-1.5">
          {HANDOUT_TYPES.map((t) => (
            <button
              key={t.value}
              onClick={() => setHandoutType(t.value)}
              className={cn(
                "text-[10px] px-2 py-1 rounded-lg border transition-all max-xl:min-h-11",
                handoutType === t.value
                  ? "bg-amber-500/15 text-amber-300 border-amber-500/30"
                  : "text-slate-500 border-white/5 hover:text-slate-300 hover:bg-white/4"
              )}
            >
              {t.icon} {t.label}
            </button>
          ))}
        </div>
        {/* Tone & spoiler */}
        <div className="flex gap-3">
          <div className="flex items-center gap-1.5">
            <span className="text-[10px] text-slate-600">Tone:</span>
            <select
              value={tone}
              onChange={(e) => setTone(e.target.value)}
              className="input-cyber py-0.5 text-[10px] w-24"
            >
              {HANDOUT_TONES.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="text-[10px] text-slate-600">Spoilers:</span>
            <select
              value={spoilerLevel}
              onChange={(e) => setSpoilerLevel(e.target.value)}
              className="input-cyber py-0.5 text-[10px] w-20"
            >
              {SPOILER_LEVELS.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
        </div>
      </div>

      {/* Handout content */}
      <div className="flex-1 overflow-y-auto px-4 py-3">
        {mutation.isPending && !handout && (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="w-5 h-5 text-slate-600 animate-spin" />
          </div>
        )}
        {mutation.isError && (
          <div className="text-xs text-red-400 text-center py-4">
            {gmErrorMessage(mutation.error, "Failed to generate handout. Try again.")}
          </div>
        )}
        {handout && (
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold text-slate-200">{handout.title}</h3>
              <div className="flex items-center gap-1.5">
                <span className="text-[10px] bg-white/5 px-1.5 py-0.5 rounded text-slate-500">{handout.handout_type}</span>
                <span className={cn(
                  "text-[10px] px-1.5 py-0.5 rounded",
                  handout.spoiler_level === "full" ? "bg-red-500/15 text-red-400" :
                  handout.spoiler_level === "partial" ? "bg-amber-500/15 text-amber-400" :
                  "bg-emerald-500/15 text-emerald-400"
                )}>
                  {handout.spoiler_level}
                </span>
              </div>
            </div>
            <div className="glass-dark rounded-xl border border-white/5 p-4">
              <div className="prose prose-sm prose-invert max-w-none text-xs text-slate-300 leading-relaxed whitespace-pre-wrap">
                {handout.content}
              </div>
            </div>
            {handout.related_entities.length > 0 && (
              <div className="flex flex-wrap gap-1.5">
                {handout.related_entities.map((e, i) => (
                  <span key={i} className="text-[10px] bg-cyan-500/10 text-cyan-400 px-2 py-0.5 rounded-lg border border-cyan-500/20">
                    {e}
                  </span>
                ))}
              </div>
            )}
            {/* CF-14 — publish this handout to the story's share link */}
            <div className="border-t border-white/5 pt-3 space-y-2" data-testid="handout-share">
              {!published ? (
                <>
                  <button
                    onClick={() => publish.mutate()}
                    disabled={!storyId || publish.isPending}
                    className="btn-cyber text-xs inline-flex items-center gap-1.5"
                    data-testid="handout-publish"
                  >
                    {publish.isPending ? (
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    ) : (
                      <Link2 className="w-3.5 h-3.5" />
                    )}
                    Publish to players
                  </button>
                  {!storyId && (
                    <p className="text-[10px] text-slate-600">Pick a story first — share links are per story.</p>
                  )}
                  {publish.isError && (
                    <p className="text-[10px] text-red-400" data-testid="handout-publish-error">
                      Couldn&apos;t publish — try again.
                    </p>
                  )}
                </>
              ) : (
                <div className="flex items-center gap-2" data-testid="handout-share-link">
                  <code className="flex-1 min-w-0 truncate text-[11px] text-emerald-300 bg-emerald-500/5 border border-emerald-500/20 rounded px-2 py-1.5">
                    {shareUrl}
                  </code>
                  <button
                    onClick={() => {
                      navigator.clipboard?.writeText(shareUrl).then(() => {
                        setCopied(true);
                        setTimeout(() => setCopied(false), 1500);
                      });
                    }}
                    className="flex-shrink-0 text-xs px-2 py-1.5 rounded border border-white/10 text-slate-400 hover:text-slate-200"
                    aria-label="Copy share link"
                  >
                    {copied ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
                  </button>
                  <button
                    onClick={() => unpublish.mutate()}
                    disabled={unpublish.isPending}
                    className="flex-shrink-0 text-xs px-2 py-1.5 rounded border border-white/10 text-slate-400 hover:text-red-300"
                    data-testid="handout-unpublish"
                  >
                    Unpublish
                  </button>
                </div>
              )}
            </div>
          </div>
        )}
        {!mutation.isPending && !handout && (
          <div className="text-center py-8">
            <Scroll className="w-8 h-8 text-slate-700 mx-auto mb-2" />
            <p className="text-xs text-slate-600">Choose a handout type and click Generate</p>
          </div>
        )}
      </div>
    </div>
  );
}
