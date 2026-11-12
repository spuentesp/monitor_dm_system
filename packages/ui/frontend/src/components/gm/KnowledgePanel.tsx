"use client";

import { useState } from "react";
import { AlertTriangle, Brain, Loader2, Search } from "lucide-react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { entitiesApi } from "@/lib/api";
import { gmTableApi } from "@/lib/gm-table-api";
import type { KnowledgeItem } from "@/lib/gm-table-types";
import { cn } from "@/lib/utils";

/**
 * Knowledge inspector (CF-15 / G09).
 *
 * "What do they know?" is answerable elsewhere; this panel answers "is
 * that right?". Every attributed fact, memory and pending proposal comes
 * with where it came from, and the doubtful attributions are marked. The
 * GM can challenge one, which stages a correction in the CF-8 queue — it
 * never writes canon.
 */

const SOURCE_LABELS: Record<string, string> = {
  scene: "from a scene",
  witnessed: "witnessed",
  common: "common knowledge",
  proposal: "pending proposal",
  memory: "their memory",
};

interface KnowledgePanelProps {
  universeId: string | null;
}

export function KnowledgePanel({ universeId }: KnowledgePanelProps) {
  const [selected, setSelected] = useState<string | null>(null);
  const [challenged, setChallenged] = useState<string[]>([]);

  const characters = useQuery({
    queryKey: ["gm-knowledge-characters", universeId],
    queryFn: () => entitiesApi.listNPCs({ entity_type: "character", limit: 100 }),
    enabled: !!universeId,
    staleTime: 60_000,
  });

  const audit = useQuery({
    queryKey: ["gm-knowledge-audit", universeId, selected],
    queryFn: () => gmTableApi.auditKnowledge(universeId!, selected!),
    enabled: !!universeId && !!selected,
  });

  const challenge = useMutation({
    mutationFn: (item: KnowledgeItem) =>
      gmTableApi.challengeKnowledge(universeId!, selected!, {
        item_id: item.id,
        item_kind: item.kind,
        statement: item.statement,
        reason: "The GM doubts this attribution.",
        action: "retract",
      }),
    onSuccess: (_data, item) => setChallenged((prev) => [...prev, item.id]),
  });

  if (!universeId) {
    return (
      <p className="text-[10px] text-slate-600">Select a universe to inspect knowledge.</p>
    );
  }

  return (
    <div className="space-y-3">
      <div>
        <h4 className="text-[9px] font-bold tracking-widest uppercase text-slate-500 mb-1">
          Who do you want to inspect?
        </h4>
        <div className="flex flex-wrap gap-1">
          {(characters.data?.items ?? []).map((c) => (
            <button
              key={c.id}
              type="button"
              onClick={() => setSelected(c.id)}
              className={cn(
                "text-[10px] px-2 py-0.5 rounded border transition-all",
                selected === c.id
                  ? "bg-emerald-500/15 text-emerald-300 border-emerald-500/30"
                  : "text-slate-500 border-white/5 hover:text-slate-300",
              )}
            >
              {c.name}
            </button>
          ))}
          {(characters.data?.items ?? []).length === 0 && (
            <p className="text-[10px] text-slate-600">No characters in this universe yet.</p>
          )}
        </div>
      </div>

      {audit.isPending && (
        <div className="flex items-center justify-center py-4">
          <Loader2 className="w-4 h-4 text-slate-600 animate-spin" />
        </div>
      )}
      {audit.isError && <p className="text-[10px] text-red-400">The audit failed — try again.</p>}

      {audit.data && (
        <div className="space-y-2">
          <div className="flex items-center gap-2 text-[10px] text-slate-500">
            <Brain className="w-3.5 h-3.5 text-cyan-400" />
            <span>
              {audit.data.fact_count} facts · {audit.data.memory_count} memories ·{" "}
              {audit.data.proposal_count} pending
            </span>
            {audit.data.suspicious_count > 0 && (
              <span className="text-amber-400">
                {audit.data.suspicious_count} doubtful
              </span>
            )}
          </div>

          {audit.data.items.length === 0 && (
            <p className="text-[10px] text-slate-600">
              The system attributes nothing to this character yet.
            </p>
          )}

          {audit.data.items.map((item) => (
            <div
              key={`${item.kind}-${item.id}`}
              className={cn(
                "glass-dark rounded-lg border p-2.5 space-y-1",
                item.suspicious ? "border-amber-500/30" : "border-white/5",
              )}
            >
              <div className="flex items-start gap-2">
                <p className="text-[11px] text-slate-300 flex-1 leading-relaxed">{item.statement}</p>
                {item.suspicious && (
                  <AlertTriangle
                    className="w-3.5 h-3.5 text-amber-400 flex-shrink-0"
                    aria-label="Doubtful attribution"
                  />
                )}
              </div>
              <div className="flex items-center gap-2">
                <span className="text-[9px] text-slate-600">
                  {SOURCE_LABELS[item.source] ?? item.source}
                </span>
                {item.suspicion_reason && (
                  <span className="text-[9px] text-amber-400/90">{item.suspicion_reason}</span>
                )}
                {challenged.includes(item.id) ? (
                  <span className="text-[9px] text-emerald-400 ml-auto">challenged</span>
                ) : (
                  <button
                    type="button"
                    onClick={() => challenge.mutate(item)}
                    disabled={challenge.isPending}
                    className="ml-auto text-[9px] text-slate-500 hover:text-slate-200 flex items-center gap-1"
                    aria-label="Challenge this attribution"
                  >
                    {challenge.isPending ? (
                      <Loader2 className="w-3 h-3 animate-spin" />
                    ) : (
                      <Search className="w-3 h-3" />
                    )}
                    Challenge
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default KnowledgePanel;
