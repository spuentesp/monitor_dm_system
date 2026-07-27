"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import { AlertTriangle, Compass, Globe2, Sparkles, User } from "lucide-react";
import type { ArchitectPriorityGap, Message } from "@/lib/types";
import { cn, formatRelativeTime } from "@/lib/utils";

interface WorldChangesMeta extends Record<string, unknown> {
  committed?: number;
  proposals?: number;
  universe_id?: string;
  known_open_questions?: string[];
  coverage_summary?: string;
  priority_gaps?: ArchitectPriorityGap[];
}

function WorldChangesCard({ meta }: { meta: WorldChangesMeta }) {
  const committed = Number(meta.committed ?? 0);
  const proposals = Number(meta.proposals ?? 0);
  const universeId = typeof meta.universe_id === "string" ? meta.universe_id : null;
  const questions = Array.isArray(meta.known_open_questions)
    ? meta.known_open_questions.map(String).slice(0, 3)
    : [];
  if (committed === 0 && proposals === 0 && !universeId) return null;

  return (
    <div className="mt-2 rounded-lg border border-emerald-500/20 bg-emerald-500/5 px-3 py-2 space-y-1.5 text-[11px]">
      <div className="flex items-center gap-1.5 font-medium text-emerald-300">
        <Sparkles className="w-3 h-3" />
        World changes
      </div>
      <div className="flex flex-wrap gap-1.5">
        {committed > 0 && (
          <span className="px-1.5 py-0.5 rounded bg-emerald-500/15 text-emerald-300">
            {committed} canonized
          </span>
        )}
        {proposals > 0 && (
          <span className="px-1.5 py-0.5 rounded bg-amber-500/15 text-amber-300">
            {proposals} proposal{proposals !== 1 ? "s" : ""} pending review
          </span>
        )}
      </div>
      {questions.length > 0 && (
        <ul className="space-y-0.5 text-slate-400">
          {questions.map((q) => (
            <li key={q} className="flex items-start gap-1.5">
              <span className="text-emerald-500/70 mt-px">?</span> {q}
            </li>
          ))}
        </ul>
      )}
      {universeId && (
        <Link
          href={`/forge/worlds?universe=${universeId}`}
          className="inline-flex items-center gap-1 text-emerald-300 hover:text-emerald-200 underline-offset-2 hover:underline"
        >
          <Globe2 className="w-3 h-3" /> Open in Worlds tree →
        </Link>
      )}
    </div>
  );
}

/**
 * Priority gaps + coverage summary derived by WorldArchitect
 * (FORGE_EXPANSION.md §2 finding: previously computed but never rendered).
 * Chips reuse the coverage-panel status idiom (icon + text); clicking one
 * pre-fills the composer with the gap's example prompt.
 */
function PriorityGapsCard({
  meta,
  onSuggest,
}: {
  meta: WorldChangesMeta;
  onSuggest?: (prompt: string) => void;
}) {
  const summary = typeof meta.coverage_summary === "string" ? meta.coverage_summary : "";
  const gaps = Array.isArray(meta.priority_gaps) ? meta.priority_gaps : [];
  if (!summary && gaps.length === 0) return null;

  return (
    <div className="mt-2 rounded-lg border border-amber-500/20 bg-amber-500/5 px-3 py-2 space-y-1.5 text-[11px]">
      <div className="flex items-center gap-1.5 font-medium text-amber-300">
        <AlertTriangle className="w-3 h-3" />
        Coverage gaps
      </div>
      {summary && <p className="text-slate-500 leading-snug">{summary}</p>}
      {gaps.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {gaps.map((gap, i) => (
            <button
              key={`${gap.area}-${i}`}
              type="button"
              onClick={() => gap.example_prompt && onSuggest?.(gap.example_prompt)}
              disabled={!onSuggest || !gap.example_prompt}
              title={gap.suggestion}
              className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-amber-500/15 text-amber-300 hover:bg-amber-500/25 disabled:cursor-default transition-colors"
            >
              <span className="text-amber-500/70">#{gap.priority}</span>
              {gap.area}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

/**
 * World Architect chat bubble. Simpler than PlayMessageBubble — no dice,
 * no social continuity chips. Renders a "World changes" card and a
 * priority-gaps card when the GM message has `metadata.type === "world_architect"`.
 */
export function ArchitectMessageBubble({
  msg,
  onSuggest,
}: {
  msg: Message;
  onSuggest?: (prompt: string) => void;
}) {
  const isUser = msg.role === "player";
  const meta = (msg.metadata ?? {}) as WorldChangesMeta;
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className={cn("flex gap-2.5 items-end", isUser && "flex-row-reverse")}
    >
      <div
        className={cn(
          "w-6 h-6 rounded-full border flex items-center justify-center flex-shrink-0",
          isUser
            ? "bg-cyan-500/10 border-cyan-500/25"
            : "bg-purple-500/10 border-purple-500/25",
        )}
      >
        {isUser ? (
          <User className="w-3 h-3 text-cyan-400" />
        ) : (
          <Compass className="w-3 h-3 text-purple-400" />
        )}
      </div>
      <div
        className={cn(
          "max-w-[80%] rounded-xl px-4 py-3 text-sm leading-relaxed",
          isUser
            ? "bg-cyan-500/10 border border-cyan-500/15 text-slate-200 rounded-br-sm"
            : "bg-purple-500/8 border border-purple-500/15 text-slate-300 rounded-bl-sm",
        )}
      >
        <p className="whitespace-pre-wrap">{msg.content}</p>
        {!isUser && meta.type === "world_architect" && (
          <>
            <WorldChangesCard meta={meta} />
            <PriorityGapsCard meta={meta} onSuggest={onSuggest} />
          </>
        )}
        <p
          className={cn(
            "text-[10px] mt-1",
            isUser ? "text-cyan-600 text-right" : "text-purple-700",
          )}
        >
          {formatRelativeTime(msg.timestamp)}
        </p>
      </div>
    </motion.div>
  );
}