"use client";

import { AlertTriangle, Scale } from "lucide-react";
import type { EncounterDifficulty } from "@/lib/types";
import { cn } from "@/lib/utils";

/**
 * Encounter difficulty badge (CF-13 / G06).
 *
 * The label is the point; the working is the trust. A GM who cannot check
 * the arithmetic will not believe the verdict, so the badge shows the
 * threat, the party budget and the ratio behind the word.
 */

const LABEL_STYLES: Record<string, string> = {
  trivial: "border-emerald-500/30 bg-emerald-500/10 text-emerald-300",
  easy: "border-teal-500/30 bg-teal-500/10 text-teal-300",
  moderate: "border-amber-500/30 bg-amber-500/10 text-amber-300",
  hard: "border-orange-500/30 bg-orange-500/10 text-orange-300",
  deadly: "border-red-500/30 bg-red-500/10 text-red-300",
  unrated: "border-slate-500/30 bg-slate-500/10 text-slate-400",
};

interface DifficultyBadgeProps {
  difficulty: EncounterDifficulty;
  className?: string;
}

export function DifficultyBadge({ difficulty, className }: DifficultyBadgeProps) {
  const label = difficulty.label || "unrated";
  const style = LABEL_STYLES[label] ?? LABEL_STYLES.unrated;
  const ratio = difficulty.ratio === null ? null : `${difficulty.ratio.toFixed(2)}x`;

  return (
    <div
      className={cn("glass-dark rounded-lg border border-white/5 p-2.5 space-y-1", className)}
      title={difficulty.rationale}
      data-testid="difficulty-badge"
    >
      <div className="flex items-center gap-2">
        {label === "deadly" ? (
          <AlertTriangle className="w-3.5 h-3.5 text-red-400" />
        ) : (
          <Scale className="w-3.5 h-3.5 text-slate-400" />
        )}
        <span
          className={cn(
            "text-[10px] font-bold uppercase tracking-widest px-1.5 py-0.5 rounded border",
            style,
          )}
        >
          {label}
        </span>
        {ratio && <span className="text-[10px] text-slate-500">{ratio}</span>}
      </div>
      <p className="text-[11px] text-slate-400 leading-relaxed">{difficulty.rationale}</p>
    </div>
  );
}

export default DifficultyBadge;
