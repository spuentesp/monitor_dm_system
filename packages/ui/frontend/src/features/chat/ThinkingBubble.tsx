"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Brain, ChevronDown, ChevronUp } from "lucide-react";
import { cn } from "@/lib/utils";
import type { ThinkingTrace } from "./types";

export interface ThinkingBubbleProps {
  trace: ThinkingTrace;
  /** Default expanded state. When undefined, defaults to expanded while
   *  streaming, collapsed once finished. */
  defaultExpanded?: boolean;
  className?: string;
}

/**
 * Collapsible reasoning block for an assistant message.
 *
 * Renders the CoT text the model produced before its narrative answer.
 * While the trace is still streaming (more `thinking` events arriving)
 * the bubble stays expanded so the user sees the reasoning live; once
 * `thinking_end` fires it auto-collapses so it doesn't take up screen
 * real estate in long sessions.
 */
export function ThinkingBubble({ trace, defaultExpanded, className }: ThinkingBubbleProps) {
  const initial = defaultExpanded ?? trace.streaming;
  const [expanded, setExpanded] = useState(initial);

  // Auto-collapse when streaming finishes — but only if the user hasn't
  // manually expanded it. (We can't distinguish user vs auto expand in
  // state alone, but a reasonable heuristic: if they're already expanded,
  // leave them alone.)
  const isLive = trace.streaming;
  const effectiveExpanded = expanded || isLive;

  if (!trace.text) return null;

  return (
    <div
      className={cn(
        "mt-2 rounded-lg border border-violet-500/15 bg-violet-500/[0.03] overflow-hidden",
        className,
      )}
    >
      <button
        onClick={() => setExpanded((v) => !v)}
        aria-expanded={effectiveExpanded}
        aria-label={effectiveExpanded ? "Collapse reasoning" : "Expand reasoning"}
        className="w-full flex items-center gap-2 px-2.5 py-1.5 text-left hover:bg-violet-500/5 transition-colors"
      >
        <Brain
          className={cn(
            "w-3 h-3 flex-shrink-0",
            isLive ? "text-violet-300 animate-pulse" : "text-violet-400/70",
          )}
        />
        <span className="text-[10px] font-semibold uppercase tracking-wider text-violet-300/80">
          {isLive ? "Reasoning…" : "Reasoning"}
        </span>
        {!effectiveExpanded && (
          <span className="text-[10px] text-slate-500 truncate">
            {trace.text.length > 60 ? `${trace.text.slice(0, 60).trim()}…` : trace.text.trim()}
          </span>
        )}
        <span className="ml-auto text-slate-600">
          {effectiveExpanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
        </span>
      </button>

      <AnimatePresence initial={false}>
        {effectiveExpanded && (
          <motion.div
            key="content"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.15 }}
            className="overflow-hidden border-t border-violet-500/10"
          >
            <div
            data-testid="thinking-body"
            className="px-3 py-2 text-[11px] text-slate-400 leading-relaxed whitespace-pre-wrap font-mono max-h-48 overflow-y-auto"
          >
              {trace.text}
              {isLive && (
                <span className="inline-block w-1 h-3 bg-violet-400 ml-0.5 align-middle animate-pulse" />
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}