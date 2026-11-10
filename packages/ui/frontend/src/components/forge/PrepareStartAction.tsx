"use client";

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Loader2, Sparkles } from "lucide-react";
import { ingestApi } from "@/lib/api";

// ─── Prepare a starting situation (MP-7 / join task 11) ─────────

export function PrepareStartAction({ packId, universeId }: { packId: string; universeId: string }) {
  const [prepared, setPrepared] = useState<{ location?: string; npcCount: number } | null>(null);

  const prepareMutation = useMutation({
    mutationFn: () => ingestApi.prepareStartingSituation(packId, universeId),
    onSuccess: (res) => {
      setPrepared({
        location: res.materialized?.location,
        npcCount: (res.materialized?.npcs ?? []).length,
      });
    },
  });

  return (
    <div className="flex flex-col items-center gap-2">
      <button
        className="btn-cyber text-xs gap-1"
        disabled={prepareMutation.isPending || prepared !== null}
        onClick={() => prepareMutation.mutate()}
      >
        {prepareMutation.isPending
          ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
          : <><Sparkles className="h-3.5 w-3.5" /> Prepare a starting situation</>}
      </button>
      {prepared && (
        <p className="text-xs text-emerald-400">
          Starting situation ready{prepared.location ? ` — ${prepared.location}` : ""}
          {prepared.npcCount > 0
            ? ` with ${prepared.npcCount} NPC${prepared.npcCount !== 1 ? "s" : ""} present`
            : ""}.
        </p>
      )}
      {prepareMutation.isError && (
        <p className="text-xs text-red-400">{String(prepareMutation.error)}</p>
      )}
    </div>
  );
}
