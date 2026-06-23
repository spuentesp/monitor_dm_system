"use client";

import { Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { LIVE_JOB_STATUSES, TERMINAL_JOB_STATUSES } from "./ingest-constants";

export function StatusBadge({ status }: { status: string }) {
  const base = "tag-dim text-[10px] flex items-center gap-1.5 px-2 py-0.5 rounded-full border transition-colors";
  const isLive = LIVE_JOB_STATUSES.has(status);
  
  const isSuccess = status === "indexed" || status === "completed" || status === "done";
  const isError = status === "error" || status === "failed" || status === "failed_non_retryable" || status === "blocked_provider" || status === "killed" || status === "cancelled";
  
  const cls = isLive
    ? "bg-amber-500/10 border-amber-500/20 text-amber-300"
    : isSuccess
      ? "bg-emerald-500/10 border-emerald-500/20 text-emerald-300"
      : isError
        ? "bg-red-500/10 border-red-500/20 text-red-300"
        : "bg-white/5 border-white/10 text-slate-400";
  
  const label = status === "saved" ? "Library only" : status;
  
  return (
    <span className={cn(base, cls)} title={status}>
      {isLive && (
        <Loader2 className="w-2.5 h-2.5 animate-spin" />
      )}
      {label}
    </span>
  );
}

