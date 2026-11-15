"use client";

import { useEffect, useState } from "react";
import { AlertTriangle, Brain, Loader2, Search } from "lucide-react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { entitiesApi, storiesApi } from "@/lib/api";
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
  const [storyId, setStoryId] = useState("");
  const [offset, setOffset] = useState(0);
  const [challenged, setChallenged] = useState<string[]>([]);
  const [editingItem, setEditingItem] = useState<KnowledgeItem | null>(null);
  const [action, setAction] = useState<"retract" | "correct">("retract");
  const [correctedText, setCorrectedText] = useState("");
  const [reason, setReason] = useState("");

  useEffect(() => {
    setSelected(null);
    setStoryId("");
    setOffset(0);
    setChallenged([]);
    setEditingItem(null);
  }, [universeId]);

  const characters = useQuery({
    queryKey: ["gm-knowledge-characters", universeId],
    queryFn: () => entitiesApi.listNPCs({ universe_id: universeId!, entity_type: "character", limit: 100 }),
    enabled: !!universeId,
    staleTime: 60_000,
  });

  const audit = useQuery({
    queryKey: ["gm-knowledge-audit", universeId, selected, offset],
    queryFn: () => gmTableApi.auditKnowledge(universeId!, selected!, offset),
    enabled: !!universeId && !!selected,
  });

  const stories = useQuery({
    queryKey: ["gm-knowledge-stories", universeId],
    queryFn: () => storiesApi.listStories({ universe_id: universeId! }),
    enabled: !!universeId,
  });

  const challenge = useMutation({
    mutationFn: (item: KnowledgeItem) =>
      gmTableApi.challengeKnowledge(universeId!, selected!, {
        item_id: item.id,
        item_kind: item.kind,
        statement: action === "correct" ? correctedText.trim() : item.statement,
        reason: reason.trim(),
        action,
        story_id: storyId,
      }),
    onSuccess: (_data, item) => {
      setChallenged((prev) => [...prev, item.id]);
      setEditingItem(null);
    },
  });

  if (!universeId) {
    return (
      <p className="text-[10px] text-slate-600">Select a universe to inspect knowledge.</p>
    );
  }

  return (
    <div className="space-y-3">
      <label className="block text-[10px] text-slate-500">
        Story for challenges
        <select aria-label="Story for challenges" value={storyId}
          onChange={(event) => setStoryId(event.target.value)} className="input-cyber ml-2 text-xs">
          <option value="">Select a story</option>
          {(stories.data?.stories ?? []).map((story) => (
            <option key={story.id} value={story.id}>{story.title}</option>
          ))}
        </select>
      </label>
      {editingItem && (
        <div className="space-y-2 rounded border border-white/10 p-2">
          <p className="text-xs text-slate-300">{editingItem.statement}</p>
          <label className="block text-xs text-slate-400">Action
            <select aria-label="Challenge action" value={action}
              onChange={(event) => setAction(event.target.value as "retract" | "correct")}
              className="input-cyber ml-2 text-xs">
              <option value="retract">Character does not know this</option>
              <option value="correct">Correct the statement</option>
            </select>
          </label>
          {action === "correct" && <textarea aria-label="Corrected statement" value={correctedText}
            onChange={(event) => setCorrectedText(event.target.value)} className="input-cyber w-full text-xs" />}
          {action === "correct" && editingItem.kind !== "memory" && (
            <p className="text-[10px] text-amber-400">This changes the underlying statement for everyone after review.</p>
          )}
          <textarea aria-label="Reason for challenge" value={reason}
            onChange={(event) => setReason(event.target.value)} className="input-cyber w-full text-xs" />
          {challenge.isError && <p className="text-xs text-red-400">Could not stage the challenge.</p>}
          <button type="button" className="btn-cyber text-xs" disabled={challenge.isPending || !reason.trim() || (action === "correct" && !correctedText.trim())}
            onClick={() => challenge.mutate(editingItem)}>Submit challenge</button>
          <button type="button" className="ml-2 text-xs" onClick={() => setEditingItem(null)}>Cancel</button>
        </div>
      )}
      <div>
        <h4 className="text-[9px] font-bold tracking-widest uppercase text-slate-500 mb-1">
          Who do you want to inspect?
        </h4>
        <div className="flex flex-wrap gap-1">
          {(characters.data?.items ?? []).map((c) => (
            <button
              key={c.id}
              type="button"
              onClick={() => { setSelected(c.id); setOffset(0); }}
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
              {" "}on this page
            </span>
            {audit.data.suspicious_count > 0 && (
              <span className="text-amber-400">
                {audit.data.suspicious_count} doubtful
              </span>
            )}
          </div>
          <div className="flex gap-2 text-xs">
            {offset > 0 && <button type="button" onClick={() => setOffset(Math.max(0, offset - 200))}>Previous page</button>}
            {audit.data.next_offset != null && <button type="button" onClick={() => setOffset(audit.data!.next_offset!)}>Next page</button>}
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
                    onClick={() => { setEditingItem(item); setAction("retract"); setCorrectedText(item.statement); setReason(""); }}
                    disabled={challenge.isPending || !storyId}
                    className="ml-auto text-[9px] text-slate-500 hover:text-slate-200 flex items-center gap-1"
                    aria-label="Challenge this attribution"
                    title="Stage this attribution for review."
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
