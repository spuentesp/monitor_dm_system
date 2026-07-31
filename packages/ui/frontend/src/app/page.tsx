"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { AnimatePresence } from "framer-motion";
import { Plus } from "lucide-react";
import { chatApi, storiesApi, universesApi } from "@/lib/api";
import { ContinuePlayingRail } from "@/components/lobby/ContinuePlayingRail";
import { NewCampaignWizard } from "@/components/lobby/NewCampaignWizard";
import { UniverseCardGrid } from "@/components/lobby/UniverseCardGrid";
import type { StorySummary } from "@/lib/types";

export default function LobbyPage() {
  const [wizardOpen, setWizardOpen] = useState(false);
  const sessionsQ = useQuery({ queryKey: ["sessions"], queryFn: chatApi.listSessions });
  const universesQ = useQuery({ queryKey: ["universes"], queryFn: () => universesApi.listUniverses() });
  const storiesQ = useQuery({
    queryKey: ["stories", "lobby"],
    queryFn: () => storiesApi.listStories({ limit: 100 }),
  });

  const latestStoryByUniverse: Record<string, StorySummary | undefined> = {};
  for (const s of storiesQ.data?.stories ?? []) {
    const prev = latestStoryByUniverse[s.universe_id];
    if (!prev || (s.created_at ?? "") > (prev.created_at ?? "")) {
      latestStoryByUniverse[s.universe_id] = s;
    }
  }

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-8 p-8">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-slate-100">Campaigns</h1>
          <p className="mt-1 text-sm text-slate-500">
            Jump back in, or start a new campaign in one of your worlds.
          </p>
        </div>
        <button
          type="button"
          onClick={() => setWizardOpen(true)}
          className="btn-cyber flex items-center gap-2 px-4 py-2 text-sm"
        >
          <Plus className="h-4 w-4" /> New campaign
        </button>
      </header>

      {sessionsQ.isError ? (
        <div
          role="alert"
          className="glass flex items-center justify-between gap-3 rounded-xl px-4 py-3 text-xs text-red-300/80"
        >
          Couldn't load recent sessions — check the backend and retry.
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
            Couldn't load your worlds — check the backend and retry.
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
