"use client";

import { useEffect, useRef, useState } from "react";
import { Swords, ArrowUp, ArrowDown, Sparkles } from "lucide-react";
import { flattenStats, readProgression } from "@/lib/combatPanel";

/**
 * Combat & progression panel (T-071).
 *
 * Complements the current-state snapshot (WorkingStateCard) by surfacing what
 * *changed* in the working state turn-over-turn (HP/resource deltas) plus an
 * XP / progression view when the loop reports it. Fully generic over whatever
 * numeric stats the game system exposes. Pure readers live in
 * `@/lib/combatPanel` so they're unit-testable.
 */

export function CombatPanel({ state }: { state: Record<string, unknown> }) {
  const current = flattenStats(state);
  const prevRef = useRef<Record<string, number>>({});
  const [deltas, setDeltas] = useState<Array<{ label: string; from: number; to: number; diff: number }>>([]);

  // Compare against the previous working state whenever it changes.
  const stateKey = JSON.stringify(current);
  useEffect(() => {
    const prev = prevRef.current;
    const changed: Array<{ label: string; from: number; to: number; diff: number }> = [];
    for (const [label, to] of Object.entries(current)) {
      const from = prev[label];
      if (typeof from === "number" && from !== to) {
        changed.push({ label, from, to, diff: to - from });
      }
    }
    if (Object.keys(prev).length > 0 && changed.length > 0) setDeltas(changed);
    prevRef.current = current;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stateKey]);

  const progression = readProgression(state);
  if (deltas.length === 0 && !progression) return null;

  return (
    <div className="glass rounded-2xl border border-white/5 p-4 space-y-3">
      <div className="flex items-center gap-2 text-slate-200">
        <Swords className="w-4 h-4 text-rose-400" />
        <h2 className="text-sm font-semibold">Combat &amp; Progression</h2>
      </div>

      {deltas.length > 0 && (
        <div className="space-y-1.5">
          <p className="text-[10px] uppercase tracking-wider text-slate-500 font-bold">Last turn</p>
          <div className="flex flex-wrap gap-1.5">
            {deltas.map((d) => {
              const up = d.diff > 0;
              return (
                <span
                  key={d.label}
                  className={
                    "text-[11px] px-2 py-1 rounded-lg border capitalize flex items-center gap-1 " +
                    (up
                      ? "border-emerald-500/20 bg-emerald-500/5 text-emerald-200"
                      : "border-rose-500/20 bg-rose-500/5 text-rose-200")
                  }
                  title={`${d.label}: ${d.from} → ${d.to}`}
                >
                  {up ? <ArrowUp className="w-3 h-3" /> : <ArrowDown className="w-3 h-3" />}
                  {d.label}
                  <span className="font-mono font-semibold">
                    {up ? "+" : ""}
                    {d.diff}
                  </span>
                </span>
              );
            })}
          </div>
        </div>
      )}

      {progression && (
        <div className="space-y-1.5">
          <div className="flex items-center justify-between text-[10px] uppercase tracking-wider text-slate-500 font-bold">
            <span className="flex items-center gap-1">
              <Sparkles className="w-3 h-3 text-amber-400" /> Progression
            </span>
            {progression.level !== undefined && (
              <span className="text-amber-300 font-mono normal-case">Lv {progression.level}</span>
            )}
          </div>
          {progression.xp !== undefined && (
            <>
              <div className="flex items-center justify-between text-[11px] text-slate-300">
                <span>XP</span>
                <span className="font-mono">
                  {progression.xp}
                  {progression.xpMax ? ` / ${progression.xpMax}` : ""}
                </span>
              </div>
              {progression.xpMax ? (
                <div className="h-1.5 rounded-full bg-white/5 overflow-hidden">
                  <div
                    className="h-full bg-gradient-to-r from-amber-500 to-amber-300"
                    style={{
                      width: `${Math.min(100, Math.round((progression.xp / progression.xpMax) * 100))}%`,
                    }}
                  />
                </div>
              ) : null}
            </>
          )}
        </div>
      )}
    </div>
  );
}
