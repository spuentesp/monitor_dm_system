"use client";

import { Loader2, X } from "lucide-react";

/**
 * "GM is thinking / writing" wait state with elapsed time and a cancel
 * (UX-6). The chat WS protocol has no server-side cancel frame, so Cancel
 * stops the client's watchdog and indicator only — the server may still
 * finish the turn in the background.
 */
export function TurnWaitBar({
  waiting,
  isWaitingForGm,
  seconds,
  onCancel,
}: {
  /** True while a turn is in flight (thinking or streaming). */
  waiting: boolean;
  /** True while waiting for the GM's first token (vs. streaming tokens). */
  isWaitingForGm: boolean;
  /** Seconds elapsed since the turn started. */
  seconds: number;
  onCancel: () => void;
}) {
  if (!waiting) return null;
  const label = isWaitingForGm ? "GM is thinking" : "GM is writing";

  return (
    <div
      role="status"
      aria-live="polite"
      data-testid="turn-wait-bar"
      className="flex items-center justify-between gap-3 rounded-xl border border-purple-500/20 bg-purple-500/5 px-3 py-2 text-xs text-purple-100"
    >
      <span className="flex items-center gap-2 min-w-0">
        <Loader2 className="h-3.5 w-3.5 flex-shrink-0 animate-spin text-purple-300" />
        <span className="truncate">
          <span className="font-medium text-purple-200">{label}</span>
          <span className="text-purple-300/80"> · {seconds}s</span>
        </span>
      </span>
      <button
        type="button"
        onClick={onCancel}
        aria-label="Cancel waiting for the GM"
        title="Stop waiting locally — the server has no cancel, so the turn may still finish"
        className="flex flex-shrink-0 items-center gap-1 rounded-lg border border-white/10 px-2 py-1 text-[11px] text-slate-300 transition-colors hover:bg-white/5 hover:text-slate-100"
      >
        <X className="h-3 w-3" />
        Cancel
      </button>
    </div>
  );
}
