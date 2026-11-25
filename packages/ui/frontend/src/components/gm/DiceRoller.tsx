"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useMutation } from "@tanstack/react-query";
import { Dices, Loader2 } from "lucide-react";
import { gmApi } from "@/lib/api";
import { cn } from "@/lib/utils";
import { uuid } from "@/lib/uuid";

interface RollResult {
  id: string;
  expression: string;
  rolls: number[];
  modifier: number;
  total: number;
  timestamp: string;
}

// Client-side input validation only — the roll itself is server-authoritative
// (POST /gm/roll); the client never generates die values.
export function isValidDiceExpression(expr: string): boolean {
  const clean = expr.trim().toLowerCase().replace(/\s/g, "");
  const match = clean.match(/^(\d+)?d(\d+)([+-]\d+)?$/);
  if (!match) return false;
  const count = parseInt(match[1] ?? "1", 10);
  const sides = parseInt(match[2], 10);
  return count >= 1 && count <= 100 && sides >= 2 && sides <= 1000;
}

const QUICK_DICE: Array<{ label: string; sides: number; color: string; border: string; bg: string }> = [
  { label: "d4",   sides: 4,   color: "text-pink-300",   border: "border-pink-500/30",   bg: "bg-pink-500/8"   },
  { label: "d6",   sides: 6,   color: "text-amber-300",  border: "border-amber-500/30",  bg: "bg-amber-500/8"  },
  { label: "d8",   sides: 8,   color: "text-orange-300", border: "border-orange-500/30", bg: "bg-orange-500/8" },
  { label: "d10",  sides: 10,  color: "text-emerald-300",border: "border-emerald-500/30",bg: "bg-emerald-500/8"},
  { label: "d12",  sides: 12,  color: "text-cyan-300",   border: "border-cyan-500/30",   bg: "bg-cyan-500/8"   },
  { label: "d20",  sides: 20,  color: "text-purple-300", border: "border-purple-500/30", bg: "bg-purple-500/8" },
  { label: "d100", sides: 100, color: "text-slate-300",  border: "border-slate-500/30",  bg: "bg-slate-500/8"  },
];

export function DiceRoller() {
  const [history, setHistory] = useState<RollResult[]>([]);
  const [expr, setExpr] = useState("1d20");
  const [diceCount, setDiceCount] = useState(1);

  const rollMutation = useMutation({
    mutationFn: (expression: string) => gmApi.rollDice(expression),
    onSuccess: (data) => {
      const entry: RollResult = {
        id: uuid(),
        expression: data.expression,
        rolls: data.rolls,
        modifier: data.modifier,
        total: data.total,
        timestamp: new Date().toLocaleTimeString(),
      };
      setHistory((h) => [entry, ...h].slice(0, 20));
    },
  });

  const doRoll = (expression: string) => {
    if (!isValidDiceExpression(expression)) return;
    rollMutation.mutate(expression);
  };

  const exprValid = isValidDiceExpression(expr);

  return (
    <div className="flex flex-col h-full space-y-4 overflow-hidden">
      {/* Quick dice */}
      <div className="grid grid-cols-4 gap-2">
        {QUICK_DICE.map((d) => (
          <button
            key={d.sides}
            onClick={() => doRoll(`${diceCount}d${d.sides}`)}
            className={cn("flex flex-col items-center gap-1 py-3 rounded-xl border transition-all hover:scale-105 active:scale-95", d.border, d.bg)}
          >
            <Dices className={cn("w-4 h-4", d.color)} />
            <span className={cn("text-xs font-bold", d.color)}>{d.label}</span>
          </button>
        ))}
      </div>

      {/* Dice count */}
      <div className="flex items-center gap-3">
        <label className="text-xs text-slate-500 w-20">Dice count</label>
        <input
          type="number"
          min={1}
          max={20}
          value={diceCount}
          onChange={(e) => setDiceCount(Math.max(1, Math.min(20, parseInt(e.target.value, 10) || 1)))}
          className="w-14 rounded border border-white/10 bg-white/4 px-2 py-1.5 text-center text-sm font-bold text-slate-200 focus:border-cyan-500/50 focus:outline-none"
        />
      </div>

      {/* Expression input */}
      <div className="flex gap-2">
        <input
          data-testid="dice-expr"
          value={expr}
          onChange={(e) => setExpr(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") doRoll(expr); }}
          placeholder="e.g. 2d6+3"
          className="input-cyber flex-1 text-sm font-mono"
        />
        <button
          onClick={() => doRoll(expr)}
          disabled={!exprValid || rollMutation.isPending}
          className={cn("btn-cyber px-3", (!exprValid || rollMutation.isPending) && "opacity-40 cursor-not-allowed")}
        >
          {rollMutation.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Dices className="w-4 h-4" />}
        </button>
      </div>

      {/* Roll history */}
      <div className="flex-1 overflow-y-auto space-y-2 min-h-0">
        <AnimatePresence initial={false}>
          {history.map((roll) => {
            const isCrit = roll.rolls.length > 0 && Math.max(...roll.rolls) >= parseInt(roll.expression.split("d")[1] ?? "0", 10);
            const isFumble = roll.rolls.length > 0 && Math.max(...roll.rolls) === 1 && roll.rolls.every((r) => r === 1);
            return (
              <motion.div
                key={roll.id}
                data-gm-entry
                initial={{ opacity: 0, x: 12 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -12 }}
                className={cn(
                  "glass-dark rounded-xl border px-3 py-2.5",
                  isCrit ? "border-amber-500/30 bg-amber-500/5" : isFumble ? "border-red-500/30 bg-red-500/5" : "border-white/5",
                )}
              >
                <div className="flex items-center justify-between">
                  <span className="text-xs font-mono text-slate-400">{roll.expression}</span>
                  <span className={cn("text-sm font-bold", isCrit ? "text-amber-300" : isFumble ? "text-red-400" : "text-slate-100")}>
                    {roll.total}
                  </span>
                </div>
                <div className="flex items-center justify-between mt-0.5">
                  <span className="text-[10px] text-slate-600">
                    [{roll.rolls.join(", ")}]{roll.modifier !== 0 ? ` ${roll.modifier > 0 ? "+" : ""}${roll.modifier}` : ""}
                  </span>
                  <span className="text-[10px] text-slate-700">{roll.timestamp}</span>
                </div>
              </motion.div>
            );
          })}
        </AnimatePresence>
        {history.length === 0 && (
          <div className="text-center py-8">
            <Dices className="w-8 h-8 text-slate-700 mx-auto mb-2" />
            <p className="text-xs text-slate-600">No rolls yet</p>
          </div>
        )}
      </div>
    </div>
  );
}
