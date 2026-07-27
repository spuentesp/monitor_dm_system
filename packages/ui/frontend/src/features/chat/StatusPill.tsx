"use client";

import { cn } from "@/lib/utils";
import type { ChatStatus } from "./types";

/** Small pill that shows the live WS connection status. */
export function StatusPill({
  status,
  onRetry,
}: {
  status: ChatStatus;
  onRetry?: () => void;
}) {
  if (status === "connected") return null;

  const cfg =
    status === "reconnecting"
      ? { bg: "bg-yellow-500/10", text: "text-yellow-400", border: "border-yellow-500/20", label: "Reconnecting…" }
      : status === "connecting"
        ? { bg: "bg-blue-500/10", text: "text-blue-400", border: "border-blue-500/20", label: "Connecting…" }
        : { bg: "bg-red-500/10", text: "text-red-400", border: "border-red-500/20", label: "Disconnected — retry" };

  return (
    <div
      className={cn(
        "flex items-center gap-1.5 text-[10px] px-2 py-1 rounded-full",
        cfg.bg,
        cfg.text,
        cfg.border,
        "border",
      )}
    >
      <span
        className={cn(
          "w-1.5 h-1.5 rounded-full",
          cfg.text.replace("text-", "bg-"),
          status !== "disconnected" && "animate-pulse",
        )}
      />
      {status === "disconnected" && onRetry ? (
        <button onClick={onRetry} className="underline hover:opacity-80">
          {cfg.label}
        </button>
      ) : (
        cfg.label
      )}
    </div>
  );
}