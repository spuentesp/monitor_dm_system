"use client";

import { Dices } from "lucide-react";

/** Compact dice-result summary shown inside a GM bubble. */
export function DiceResultCard({
  spec,
  total,
  rolls,
  reason,
  successLevel,
}: {
  spec: string;
  total: number;
  rolls?: number[];
  reason?: string;
  successLevel?: string;
}) {
  return (
    <div className="mt-2 rounded-lg border border-purple-500/20 bg-purple-500/5 px-2.5 py-2 text-[11px] space-y-1.5">
      <div className="flex items-center gap-1.5 text-purple-300 font-medium">
        <Dices className="w-3 h-3" />
        {reason ?? spec}
      </div>
      {rolls && rolls.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {rolls.map((r, i) => (
            <span key={i} className="dice-face">
              {r}
            </span>
          ))}
        </div>
      )}
      <div className="flex items-center gap-2">
        <span className="dice-face-total">{total}</span>
        <span className="text-slate-400 font-mono text-[10px]">{spec}</span>
        {successLevel && (
          <span className="tag-purple capitalize">
            {successLevel.replace(/_/g, " ")}
          </span>
        )}
      </div>
    </div>
  );
}