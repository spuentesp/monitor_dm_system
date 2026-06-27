"use client";

import { useState } from "react";
import { Check, ChevronRight, Loader2, Wrench, XCircle } from "lucide-react";
import type { ToolCall } from "./types";
import { cn } from "@/lib/utils";

export interface ToolCallCardProps {
  call: ToolCall;
}

/**
 * Inline card for one MCP tool invocation surfaced by the GM message
 * (Phase 2B). Shows tool name, args preview, and either a pending spinner,
 * the result preview, or an error chip. Collapsible so long result previews
 * don't crowd the chat bubble.
 */
export function ToolCallCard({ call }: ToolCallCardProps) {
  const [expanded, setExpanded] = useState(false);
  const isPending = call.pending;
  const hasError = !!call.error;
  const status = isPending ? "running" : hasError ? "error" : "done";

  return (
    <div
      className={cn(
        "mt-2 rounded-lg border text-[11px] overflow-hidden",
        status === "running" && "border-violet-500/20 bg-violet-500/[0.03]",
        status === "done" && "border-emerald-500/15 bg-emerald-500/[0.03]",
        status === "error" && "border-red-500/25 bg-red-500/[0.04]",
      )}
      data-testid="tool-call-card"
    >
      <button
        onClick={() => setExpanded((v) => !v)}
        aria-expanded={expanded}
        aria-label={expanded ? `Collapse ${call.name}` : `Expand ${call.name}`}
        className="w-full flex items-center gap-2 px-2.5 py-1.5 text-left hover:bg-white/[0.02] transition-colors"
      >
        <ChevronRight
          className={cn(
            "w-3 h-3 transition-transform flex-shrink-0",
            expanded && "rotate-90",
            status === "running" && "text-violet-400",
            status === "done" && "text-emerald-400",
            status === "error" && "text-red-400",
          )}
        />
        <Wrench
          className={cn(
            "w-3 h-3 flex-shrink-0",
            status === "running" && "text-violet-400",
            status === "done" && "text-emerald-400",
            status === "error" && "text-red-400",
          )}
        />
        <span className="font-mono text-slate-300 truncate">{call.name}</span>
        <span className="ml-auto flex items-center gap-1.5 text-[10px]">
          {status === "running" && (
            <>
              <Loader2 className="w-3 h-3 text-violet-400 animate-spin" />
              <span className="text-violet-300/70">running</span>
            </>
          )}
          {status === "done" && (
            <>
              <Check className="w-3 h-3 text-emerald-400" />
              <span className="text-emerald-300/70">done</span>
            </>
          )}
          {status === "error" && (
            <>
              <XCircle className="w-3 h-3 text-red-400" />
              <span className="text-red-300/70">error</span>
            </>
          )}
        </span>
      </button>

      {expanded && (
        <div className="border-t border-white/5 px-2.5 py-2 space-y-2">
          <div>
            <div className="text-[10px] uppercase tracking-wider text-slate-600 mb-0.5">Arguments</div>
            <pre className="font-mono text-[10px] text-slate-400 whitespace-pre-wrap break-all bg-black/20 rounded px-2 py-1 max-h-32 overflow-y-auto">
              {formatArgs(call.args)}
            </pre>
          </div>
          {call.error && (
            <div>
              <div className="text-[10px] uppercase tracking-wider text-red-400/80 mb-0.5">Error</div>
              <pre className="font-mono text-[10px] text-red-200/90 whitespace-pre-wrap break-all bg-red-500/10 rounded px-2 py-1 max-h-32 overflow-y-auto">
                {call.error}
              </pre>
            </div>
          )}
          {call.result_preview !== undefined && (
            <div>
              <div className="text-[10px] uppercase tracking-wider text-emerald-400/80 mb-0.5">Result preview</div>
              <pre className="font-mono text-[10px] text-slate-300 whitespace-pre-wrap break-all bg-black/20 rounded px-2 py-1 max-h-32 overflow-y-auto">
                {call.result_preview}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/** Format the args object for display — JSON with sensible line lengths. */
function formatArgs(args: Record<string, unknown>): string {
  try {
    const json = JSON.stringify(args, null, 2);
    // Strip injected authority fields the server adds but the UI doesn't
    // need to display — they would just clutter the card.
    const stripped = json
      .replace(/[\n ]+"agent_type": "[^"]*",?/g, "")
      .replace(/[\n ]+"agent_id": "[^"]*",?/g, "");
    return stripped.trim();
  } catch {
    return String(args);
  }
}
