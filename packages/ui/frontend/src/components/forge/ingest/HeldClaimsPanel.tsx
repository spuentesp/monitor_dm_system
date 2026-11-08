"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Loader2, X } from "lucide-react";
import { ApiError, ingestApi } from "@/lib/api";
import type { HeldClaim } from "@/lib/types";
import { FORGE_KEYS } from "@/lib/query-keys";
import { useNotify } from "@/components/NotificationProvider";

/** The server's reason for refusing, without the JSON wrapper. */
export function refusalText(e: unknown): string {
  if (e instanceof ApiError) {
    try {
      const detail = JSON.parse(e.message)?.detail;
      if (typeof detail === "string") return detail;
    } catch {
      // Not JSON; the raw text is the reason.
    }
    return e.message;
  }
  return e instanceof Error ? e.message : "The decision wasn't saved.";
}

function ClaimCard({ jobId, claim }: { jobId: string; claim: HeldClaim }) {
  const queryClient = useQueryClient();
  const { notify } = useNotify();
  const [wording, setWording] = useState(claim.statement);
  const decide = useMutation({
    mutationFn: (accept: boolean) => {
      const changed = wording.trim() !== claim.statement.trim();
      return ingestApi.decideHeldClaim(jobId, claim.claim_id, accept, accept && changed ? wording.trim() : undefined);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: FORGE_KEYS.heldClaims(jobId) });
      queryClient.invalidateQueries({ queryKey: FORGE_KEYS.jobs });
      queryClient.invalidateQueries({ queryKey: FORGE_KEYS.packs });
    },
    onError: (e: unknown) => notify("error", refusalText(e)),
  });

  return (
    <li className="rounded-lg border border-white/8 bg-white/[0.02] p-2.5 space-y-2" data-testid="held-claim">
      <div className="flex items-center gap-2 text-[10px] text-slate-500">
        <span className="uppercase tracking-tight text-amber-300/80">{claim.kind}</span>
        {claim.name && <span className="text-slate-300">{claim.name}</span>}
        <span>· page {claim.page}</span>
      </div>
      <textarea
        aria-label="Claim wording"
        value={wording}
        onChange={(e) => setWording(e.target.value)}
        rows={Math.min(6, Math.max(2, Math.ceil(wording.length / 90)))}
        className="w-full resize-y rounded-md bg-black/30 border border-white/8 p-2 text-[12px] text-slate-200 leading-snug focus:outline-none focus:border-cyan-500/40"
      />
      <p className="text-[11px] text-amber-200/80 leading-snug">Why it waits: {claim.reason}</p>
      {claim.sources.length > 0 && (
        <div className="space-y-1">
          <p className="text-[10px] uppercase tracking-tight text-slate-500">The book says</p>
          {claim.sources.map((source) => (
            <blockquote key={source.id} className="border-l-2 border-cyan-500/30 pl-2 text-[11px] text-slate-400 leading-snug">
              {source.text} <span className="text-slate-600">(p. {source.page})</span>
            </blockquote>
          ))}
        </div>
      )}
      {claim.conflicts.length > 0 && (
        <div className="space-y-1">
          <p className="text-[10px] uppercase tracking-tight text-slate-500">It conflicts with</p>
          {claim.conflicts.map((other) => (
            <p key={other.claim_id} className="text-[11px] text-rose-200/80 leading-snug">{other.statement}</p>
          ))}
        </div>
      )}
      <div className="flex items-center justify-end gap-2">
        <button
          onClick={() => decide.mutate(false)}
          disabled={decide.isPending}
          className="flex items-center gap-1 px-2 py-1 rounded-lg text-[11px] text-slate-300 border border-white/10 hover:text-rose-300 hover:border-rose-500/30 disabled:opacity-50"
          title="Leave this claim out of the pack"
        >
          <X className="w-3 h-3" /> Reject
        </button>
        <button
          onClick={() => decide.mutate(true)}
          disabled={decide.isPending || !wording.trim()}
          className="flex items-center gap-1 px-2 py-1 rounded-lg text-[11px] text-emerald-300 border border-emerald-500/25 hover:bg-emerald-500/10 disabled:opacity-50"
          title="Add this wording to the book's pack"
        >
          {decide.isPending ? <Loader2 className="w-3 h-3 animate-spin" /> : <Check className="w-3 h-3" />} Accept
        </button>
      </div>
    </li>
  );
}

/** Claims a book's review couldn't settle. Accepting adds the claim to the book's pack. */
export function HeldClaimsPanel({ jobId }: { jobId: string }) {
  const { data: claims = [], isLoading, error } = useQuery<HeldClaim[]>({
    queryKey: FORGE_KEYS.heldClaims(jobId),
    queryFn: () => ingestApi.listHeldClaims(jobId),
  });
  if (isLoading) {
    return (
      <p className="flex items-center gap-2 text-[11px] text-slate-500">
        <Loader2 className="w-3 h-3 animate-spin" /> Loading claims…
      </p>
    );
  }
  if (error) return <p className="text-[11px] text-red-300">{refusalText(error)}</p>;
  const open = claims.filter((claim) => !claim.decision);
  const decided = claims.length - open.length;
  return (
    <div className="space-y-2">
      <p className="text-[11px] text-slate-400">
        {open.length === 0 ? "No claims left to review." : `${open.length} claims to review.`}
        {decided > 0 && ` ${decided} already decided.`}
      </p>
      <ul className="space-y-2 max-h-[28rem] overflow-y-auto pr-1 custom-scrollbar">
        {open.map((claim) => (
          <ClaimCard key={claim.claim_id} jobId={jobId} claim={claim} />
        ))}
      </ul>
    </div>
  );
}
