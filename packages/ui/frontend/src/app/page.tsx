"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { AnimatePresence } from "framer-motion";
import { Loader2, Plus, Zap } from "lucide-react";
import { chatApi, storiesApi, universesApi } from "@/lib/api";
import { errorMessage } from "@/lib/errors";
import { useNotify } from "@/components/NotificationProvider";
import { ContinuePlayingRail } from "@/components/lobby/ContinuePlayingRail";
import { NewCampaignWizard } from "@/components/lobby/NewCampaignWizard";
import { UniverseCardGrid } from "@/components/lobby/UniverseCardGrid";
import { createQuickStartSession } from "@/components/play/quickStart";
import { quotaMessageFor } from "@/components/play/quota";
import type { StorySummary } from "@/lib/types";

export default function LobbyPage() {
  const router = useRouter();
  const { notify } = useNotify();
  const [wizardOpen, setWizardOpen] = useState(false);
  const [quickStarting, setQuickStarting] = useState(false);
  const sessionsQ = useQuery({ queryKey: ["sessions"], queryFn: chatApi.listSessions });
  const universesQ = useQuery({ queryKey: ["universes"], queryFn: () => universesApi.listUniverses() });
  const storiesQ = useQuery({
    queryKey: ["stories", "lobby"],
    queryFn: () => storiesApi.listStories({ limit: 100 }),
  });

  // One-click Quick start (UX-6): shared with the play console's setup —
  // defaults pick the first world/system; the wizard stays as the advanced
  // path behind "New campaign".
  async function quickStart() {
    if (quickStarting) return;
    setQuickStarting(true);
    try {
      const session = await createQuickStartSession();
      router.push(`/play?session=${session.id}`);
    } catch (err) {
      notify(
        "error",
        quotaMessageFor(err) ?? `Couldn't start a campaign: ${errorMessage(err)}`,
      );
      setQuickStarting(false);
    }
  }

  const latestStoryByUniverse: Record<string, StorySummary | undefined> = {};
  for (const s of storiesQ.data?.stories ?? []) {
    const prev = latestStoryByUniverse[s.universe_id];
    if (!prev || (s.created_at ?? "") > (prev.created_at ?? "")) {
      latestStoryByUniverse[s.universe_id] = s;
    }
  }

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-8 p-4 sm:p-8">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-slate-100">Campaigns</h1>
          <p className="mt-1 text-sm text-slate-500">
            Jump back in, or start a new campaign in one of your worlds.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => void quickStart()}
            disabled={quickStarting}
            className="btn-cyber flex items-center gap-2 px-4 py-2 text-sm"
            title="One click — starts a campaign with default world, tone and system"
          >
            {quickStarting ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Zap className="h-4 w-4" />
            )}
            Quick start
          </button>
          <button
            type="button"
            onClick={() => setWizardOpen(true)}
            className="btn-ghost flex items-center gap-2 px-4 py-2 text-sm"
            title="Advanced setup — pick world, story, title and tone"
          >
            <Plus className="h-4 w-4" /> New campaign
          </button>
        </div>
      </header>

      {sessionsQ.isError ? (
        <div
          role="alert"
          className="glass flex items-center justify-between gap-3 rounded-xl px-4 py-3 text-xs text-red-300/80"
        >
          Couldn&apos;t load recent sessions — check the backend and retry.
          <button
            type="button"
            onClick={() => void sessionsQ.refetch()}
            className="btn-ghost px-3 py-1.5 text-xs"
          >
            Retry
          </button>
        </div>
      ) : (
        <ContinuePlayingRail sessions={sessionsQ.data ?? []} />
      )}

      <section aria-label="Playable universes" className="space-y-2">
        <div className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">
          Playable universes
        </div>
        {universesQ.isLoading ? (
          <div className="text-sm text-slate-500">Loading universes…</div>
        ) : universesQ.isError ? (
          <div
            role="alert"
            className="glass flex items-center justify-between gap-3 rounded-xl px-5 py-4 text-sm text-red-300/80"
          >
            Couldn&apos;t load your worlds — check the backend and retry.
            <button
              type="button"
              onClick={() => void universesQ.refetch()}
              className="btn-ghost px-3 py-1.5 text-xs"
            >
              Retry
            </button>
          </div>
        ) : (
          <UniverseCardGrid
            universes={universesQ.data ?? []}
            latestStoryByUniverse={latestStoryByUniverse}
            storiesError={storiesQ.isError}
          />
        )}
      </section>

      <AnimatePresence>
        {wizardOpen && (
          <NewCampaignWizard
            universes={universesQ.data ?? []}
            onClose={() => setWizardOpen(false)}
          />
        )}
      </AnimatePresence>
    </div>
  );
}
