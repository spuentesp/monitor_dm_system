"use client";

import { RefreshCw, WifiOff } from "lucide-react";

import type { ChatStatus } from "@/features/chat";
import { cn } from "@/lib/utils";

const STATUS_COPY: Record<Exclude<ChatStatus, "connected">, { label: string; detail: string }> = {
  reconnecting: {
    label: "Connection lost — reconnecting…",
    detail: "Retrying automatically with backoff. Your next message will send once it's back.",
  },
  connecting: {
    label: "Connecting…",
    detail: "Opening the session channel.",
  },
  disconnected: {
    label: "Disconnected.",
    detail: "The session channel is closed — it reopens when you send or reload.",
  },
};

/**
 * Visible connection state for the play console (UX-6). Rendered only while
 * a session is active; hidden entirely while the socket is connected.
 *
 * The underlying useChatWebSocket performs the automatic reconnect with
 * exponential backoff — this banner just makes that state legible.
 */
export function ConnectionBanner({ status }: { status: ChatStatus }) {
  if (status === "connected") return null;
  const copy = STATUS_COPY[status];
  const tone =
    status === "disconnected"
      ? "border-red-500/30 bg-red-500/10 text-red-200"
      : "border-amber-500/30 bg-amber-500/10 text-amber-100";

  return (
    <div
      role="status"
      aria-live="polite"
      data-testid="connection-banner"
      data-status={status}
      className={cn("flex items-start gap-2 border-b px-4 py-2 text-xs", tone)}
    >
      {status === "disconnected" ? (
        <WifiOff className="mt-0.5 h-3.5 w-3.5 flex-shrink-0" />
      ) : (
        <RefreshCw className="mt-0.5 h-3.5 w-3.5 flex-shrink-0 animate-spin" />
      )}
      <span>
        <span className="font-medium">{copy.label}</span>{" "}
        <span className="opacity-80">{copy.detail}</span>
      </span>
    </div>
  );
}
