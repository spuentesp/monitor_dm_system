"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { BookOpen, ChevronLeft, Globe2, Loader2, Sparkles, X } from "lucide-react";
import { chatApi, storiesApi } from "@/lib/api";
import { useNotify } from "@/components/NotificationProvider";
import { errorMessage } from "@/lib/errors";
import type { StorySummary, Universe } from "@/lib/types";
import { cn } from "@/lib/utils";

type Step = "universe" | "story" | "details";

const TONES = ["heroic", "gritty", "whimsical", "horror", "mystery"] as const;

/** Guided new-campaign flow: universe → story → title/tone → play. */
export function NewCampaignWizard({
  universes,
  onClose,
}: {
  universes: Universe[];
  onClose: () => void;
}) {
  const router = useRouter();
  const { notify } = useNotify();
  const [step, setStep] = useState<Step>("universe");
  const [universe, setUniverse] = useState<Universe | null>(null);
  const [story, setStory] = useState<StorySummary | null>(null); // null = brand-new story
  const [title, setTitle] = useState("");
  const [tone, setTone] = useState<string>("heroic");
  const [creating, setCreating] = useState(false);

  const storiesQ = useQuery({
    queryKey: ["stories", "wizard", universe?.id],
    queryFn: () => storiesApi.listStories({ universe_id: universe!.id, limit: 100 }),
    enabled: !!universe,
  });

  async function begin() {
    if (!universe || creating) return;
    setCreating(true);
    try {
      const session = await chatApi.createSession({
        title: title.trim() || `New ${universe.name} campaign`,
        mode: "autonomous_gm",
        universe_id: universe.id,
        universe_label: universe.name,
        story_id: story?.id ?? null,
        tone,
      });
      router.push(`/play?session=${session.id}`);
    } catch (e) {
      notify("error", `Couldn't create campaign: ${errorMessage(e)}`);
      setCreating(false);
    }
  }

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      role="dialog"
      aria-label="New campaign"
    >
      <motion.div
        initial={{ scale: 0.96, y: 8 }}
        animate={{ scale: 1, y: 0 }}
        className="glass w-full max-w-lg rounded-2xl border border-cyan-500/20 p-6"
      >
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-cyan-300">New campaign</h2>
          <button onClick={onClose} aria-label="Close" className="text-slate-600 hover:text-slate-300">
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Step indicator */}
        <div className="mb-5 flex gap-1.5">
          {(["universe", "story", "details"] as Step[]).map((s, i) => (
            <div
              key={s}
              className={cn(
                "h-1 flex-1 rounded-full",
                (["universe", "story", "details"] as Step[]).indexOf(step) >= i
                  ? "bg-cyan-500/60"
                  : "bg-white/10",
              )}
            />
          ))}
        </div>

        <AnimatePresence mode="wait">
          {step === "universe" && (
            <motion.div key="u" initial={{ opacity: 0, x: 12 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -12 }} className="space-y-2">
              <div className="text-xs text-slate-500">1 · Choose a world</div>
              {universes.map((u) => (
                <button
                  key={u.id}
                  onClick={() => {
                    setUniverse(u);
                    setStory(null);
                    setStep("story");
                  }}
                  className="glass flex w-full items-center gap-3 rounded-xl px-4 py-3 text-left transition-colors hover:border-cyan-500/30"
                >
                  <Globe2 className="h-4 w-4 flex-shrink-0 text-cyan-400" />
                  <span className="min-w-0">
                    <span className="block truncate text-sm font-medium text-slate-200">{u.name}</span>
                    <span className="block truncate text-[11px] text-slate-500">
                      {[u.genre, `${u.entity_count} entities`].filter(Boolean).join(" · ")}
                    </span>
                  </span>
                </button>
              ))}
            </motion.div>
          )}

          {step === "story" && universe && (
            <motion.div key="s" initial={{ opacity: 0, x: 12 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -12 }} className="space-y-2">
              <div className="text-xs text-slate-500">2 · Continue a story or start fresh</div>
              <button
                onClick={() => {
                  setStory(null);
                  setStep("details");
                }}
                className="glass flex w-full items-center gap-3 rounded-xl border-cyan-500/25 px-4 py-3 text-left hover:border-cyan-500/40"
              >
                <Sparkles className="h-4 w-4 flex-shrink-0 text-cyan-400" />
                <span className="text-sm font-medium text-slate-200">New story</span>
              </button>
              {storiesQ.isLoading && <div className="text-xs text-slate-600">Loading stories…</div>}
              {(storiesQ.data?.stories ?? []).map((s) => (
                <button
                  key={s.id}
                  onClick={() => {
                    setStory(s);
                    setStep("details");
                  }}
                  className="glass flex w-full items-center gap-3 rounded-xl px-4 py-3 text-left hover:border-purple-500/30"
                >
                  <BookOpen className="h-4 w-4 flex-shrink-0 text-purple-300" />
                  <span className="min-w-0">
                    <span className="block truncate text-sm font-medium text-slate-200">{s.title}</span>
                    <span className="block text-[11px] text-slate-500">
                      {s.status} · {s.scene_count} scenes
                    </span>
                  </span>
                </button>
              ))}
              <button onClick={() => setStep("universe")} className="btn-ghost flex items-center gap-1 px-2 py-1 text-xs">
                <ChevronLeft className="h-3 w-3" /> Back
              </button>
            </motion.div>
          )}

          {step === "details" && universe && (
            <motion.div key="d" initial={{ opacity: 0, x: 12 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -12 }} className="space-y-4">
              <div className="text-xs text-slate-500">
                3 · {universe.name}
                {story ? ` — ${story.title}` : " — new story"}
              </div>
              <div className="space-y-1.5">
                <label htmlFor="wizard-title" className="text-xs text-slate-500">
                  Campaign title
                </label>
                <input
                  id="wizard-title"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder={`New ${universe.name} campaign`}
                  className="input-cyber w-full"
                />
              </div>
              <div className="space-y-1.5">
                <label htmlFor="wizard-tone" className="text-xs text-slate-500">
                  Tone
                </label>
                <select
                  id="wizard-tone"
                  value={tone}
                  onChange={(e) => setTone(e.target.value)}
                  className="input-cyber w-full"
                >
                  {TONES.map((t) => (
                    <option key={t} value={t}>
                      {t}
                    </option>
                  ))}
                </select>
              </div>
              <div className="flex items-center justify-between">
                <button onClick={() => setStep("story")} className="btn-ghost flex items-center gap-1 px-2 py-1 text-xs">
                  <ChevronLeft className="h-3 w-3" /> Back
                </button>
                <button
                  onClick={begin}
                  disabled={creating}
                  className="btn-cyber flex items-center gap-2 px-4 py-2 text-sm"
                >
                  {creating ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
                  Begin campaign
                </button>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </motion.div>
    </motion.div>
  );
}
