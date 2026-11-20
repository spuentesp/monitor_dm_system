"use client";

import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, Loader2 } from "lucide-react";
import { systemApi } from "@/lib/api";

/**
 * Banner shown atop /gm when the backend/LLM is unreachable (or degraded),
 * following the ConnectionStatus query pattern (shared ["health"] cache).
 * Dice rolls and session notes keep working offline-ish states, so the
 * message says exactly that instead of a raw error.
 */
export function GmOfflineBanner() {
  const { data, error, isLoading } = useQuery({
    queryKey: ["health"],
    queryFn: () => systemApi.getHealth(),
    refetchInterval: 30_000,
    refetchOnWindowFocus: true,
  });

  if (isLoading) return null;

  const status =
    data && typeof data === "object" && "status" in data
      ? (data as { status?: string }).status
      : undefined;

  if (error) {
    return (
      <div
        data-testid="gm-offline-banner"
        role="status"
        className="mx-6 mt-3 flex items-start gap-2 rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-2.5 flex-shrink-0"
      >
        <AlertTriangle className="w-3.5 h-3.5 text-red-400 flex-shrink-0 mt-0.5" />
        <p className="text-xs text-red-300 leading-relaxed">
          Backend unreachable — AI panels (insights, contradictions, ask) won&apos;t
          respond right now. Dice and notes still work.
        </p>
      </div>
    );
  }

  if (status && status !== "ok") {
    return (
      <div
        data-testid="gm-offline-banner"
        role="status"
        className="mx-6 mt-3 flex items-start gap-2 rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-2.5 flex-shrink-0"
      >
        <Loader2 className="w-3.5 h-3.5 text-amber-400 flex-shrink-0 mt-0.5 animate-spin" />
        <p className="text-xs text-amber-300 leading-relaxed">
          Backend degraded — some AI panels may fail. Dice and notes still work.
        </p>
      </div>
    );
  }

  return null;
}
