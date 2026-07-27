"use client";

import { useEffect } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  AlertCircle,
  BookOpen,
  CheckCircle2,
  Flag,
  GitBranch,
  Loader2,
  RotateCcw,
  ShieldCheck,
  Sparkles,
  XCircle,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { chatApi } from "@/lib/api";
import type { WrapUpCanonItem } from "@/lib/types";
import { DialogShell } from "@/components/DialogShell";
import { cn } from "@/lib/utils";

function SectionHeading({
  icon: Icon,
  children,
  className,
}: {
  icon: typeof BookOpen;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-slate-500",
        className,
      )}
    >
      <Icon className="w-3 h-3" /> {children}
    </div>
  );
}

function CanonItemRow({ item }: { item: WrapUpCanonItem }) {
  const style =
    item.status === "accepted"
      ? { icon: CheckCircle2, cls: "text-emerald-400" }
      : item.status === "rejected"
        ? { icon: XCircle, cls: "text-red-400" }
        : { icon: ShieldCheck, cls: "text-amber-400" };
  return (
    <li className="flex items-start gap-2 text-xs text-slate-300">
      <style.icon className={cn("w-3.5 h-3.5 flex-shrink-0 mt-0.5", style.cls)} />
      <span>
        {item.label}
        <span className="text-slate-600"> · {item.change_type.replace("_", " ")}</span>
      </span>
    </li>
  );
}

/**
 * P1.3 — Guided end-of-session wrap-up digest for gm_assistant recordings.
 *
 * Mounting the modal fires POST /chat/{id}/wrap-up, which canonizes the open
 * scene, builds the recap, tallies canon decisions, and drafts a next-session
 * teaser. That is several LLM calls, so the modal owns a progress state and
 * an error state with retry (agents run sequentially server-side in v1).
 */
export function WrapUpModal({ sessionId, onClose }: { sessionId: string; onClose: () => void }) {
  const qc = useQueryClient();
  const wrapUp = useMutation({
    mutationFn: () => chatApi.wrapUp(sessionId),
    onSuccess: () => {
      // The session doc gained recap_text/wrapped_up_at (P1.4) — refresh the
      // recordings list so the dropdown shows the "wrapped up" marker.
      qc.invalidateQueries({ queryKey: ["sessions"] });
      qc.invalidateQueries({ queryKey: ["session-recap", sessionId] });
    },
  });
  const { mutate } = wrapUp;

  useEffect(() => {
    mutate();
  }, [mutate]);

  const digest = wrapUp.data;

  return (
    <DialogShell
      title="Session wrap-up"
      icon={Flag}
      iconClassName="text-amber-400"
      onClose={onClose}
      maxWidthClassName="max-w-2xl"
    >
      <div className="p-5 max-h-[65vh] overflow-y-auto space-y-5">
        {wrapUp.isPending ? (
          <div
            data-testid="wrap-up-loading"
            className="flex items-center gap-3 py-10 justify-center text-slate-500"
          >
            <Loader2 className="w-5 h-5 animate-spin" />
            <span className="text-sm">
              Wrapping up — canonizing the scene, gathering the threads…
            </span>
          </div>
        ) : wrapUp.isError ? (
          <div
            data-testid="wrap-up-error"
            className="flex flex-col items-center gap-3 py-8 text-center"
          >
            <AlertCircle className="w-8 h-8 text-red-500/60" />
            <p className="text-sm text-slate-400">
              {wrapUp.error instanceof Error ? wrapUp.error.message : "Couldn't wrap up the session."}
            </p>
            <button onClick={() => wrapUp.mutate()} className="btn-cyber text-xs">
              <RotateCcw className="w-3.5 h-3.5" /> Try again
            </button>
          </div>
        ) : digest ? (
          <>
            {/* Recap */}
            <section data-testid="wrap-up-recap" className="space-y-2">
              <SectionHeading icon={BookOpen}>Recap</SectionHeading>
              <div className="prose-bubble text-sm text-slate-300 leading-relaxed">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{digest.recap}</ReactMarkdown>
              </div>
            </section>

            {/* Canon changes */}
            <section data-testid="wrap-up-canon" className="space-y-2">
              <SectionHeading icon={ShieldCheck}>Canon changes</SectionHeading>
              <div className="flex items-center gap-2 text-[11px]">
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full border border-emerald-500/20 bg-emerald-500/5 text-emerald-300">
                  <CheckCircle2 className="w-3 h-3" /> {digest.accepted} accepted
                </span>
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full border border-red-500/20 bg-red-500/5 text-red-300">
                  <XCircle className="w-3 h-3" /> {digest.rejected} rejected
                </span>
                {digest.pending > 0 && (
                  <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full border border-amber-500/20 bg-amber-500/5 text-amber-300">
                    <ShieldCheck className="w-3 h-3" /> {digest.pending} pending
                  </span>
                )}
              </div>
              {digest.canon_items.length > 0 ? (
                <ul className="space-y-1.5">
                  {digest.canon_items.map((item) => (
                    <CanonItemRow key={item.proposal_id} item={item} />
                  ))}
                </ul>
              ) : (
                <p className="text-xs text-slate-600">No canon changes were proposed this session.</p>
              )}
            </section>

            {/* Open threads */}
            <section data-testid="wrap-up-threads" className="space-y-2">
              <SectionHeading icon={GitBranch}>Open threads</SectionHeading>
              {digest.open_threads.length > 0 ? (
                <div className="flex flex-wrap gap-1.5">
                  {digest.open_threads.map((thread) => (
                    <span
                      key={thread}
                      className="text-[10px] px-2 py-0.5 rounded-full border border-purple-500/20 bg-purple-500/5 text-purple-300"
                    >
                      {thread}
                    </span>
                  ))}
                </div>
              ) : (
                <p className="text-xs text-slate-600">No dangling threads on the board.</p>
              )}
            </section>

            {/* Next session teaser */}
            <section data-testid="wrap-up-next-prep" className="space-y-2">
              <SectionHeading icon={Sparkles}>Next session teaser</SectionHeading>
              {digest.next_prep && digest.next_prep.hooks.length > 0 ? (
                <ul className="space-y-1.5">
                  {digest.next_prep.hooks.map((hook, i) => (
                    <li key={`${hook.title}-${i}`} className="text-xs text-slate-300">
                      <span className="font-semibold text-slate-200">{hook.title}</span>
                      <span className="text-slate-500"> — {hook.description}</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-xs text-slate-600">
                  No hooks drafted — the next session starts with a blank page.
                </p>
              )}
              {digest.next_prep && digest.next_prep.npc_reminders.length > 0 && (
                <p className="text-[11px] text-slate-500">
                  Remember: {digest.next_prep.npc_reminders.join(", ")}
                </p>
              )}
            </section>
          </>
        ) : null}
      </div>
    </DialogShell>
  );
}
