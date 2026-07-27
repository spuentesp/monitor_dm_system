"use client";

import {
  Archive,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Loader2,
  Clock,
} from "lucide-react";

export function JobIcon({ status, className }: { status: string; className?: string }) {
  if (status === "completed" || status === "done")
    return <CheckCircle2 className={className ?? "w-4 h-4 text-emerald-400 flex-shrink-0"} />;
  if (status === "partial")
    return <AlertTriangle className={className ?? "w-4 h-4 text-amber-300 flex-shrink-0"} />;
  if (status === "error" || status === "failed" || status === "failed_non_retryable" || status === "blocked_provider" || status === "killed" || status === "cancelled")
    return <XCircle className={className ?? "w-4 h-4 text-red-400 flex-shrink-0"} />;
  if (status === "saved")
    return <Archive className={className ?? "w-4 h-4 text-amber-300 flex-shrink-0"} />;
  if (status === "running" || status === "pending" || status === "retrying" || status === "backing_off" || status === "draft")
    return <Loader2 className={className ?? "w-4 h-4 text-cyan-400 animate-spin flex-shrink-0"} />;
  return <Clock className={className ?? "w-4 h-4 text-slate-500 flex-shrink-0"} />;
}
