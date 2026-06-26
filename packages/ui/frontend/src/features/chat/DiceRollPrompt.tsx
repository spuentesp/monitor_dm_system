"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import { Dices } from "lucide-react";
import { cn } from "@/lib/utils";
import type { DiceRequest } from "./types";

/** Dice roller with auto + manual entry. Mirrors data-layer/utils/dice.py. */
function clientRollDice(spec: string): { total: number; rolls: number[]; mod: number } {
  const m = spec.trim().match(/^(\d*)d(\d+)([+-]\d+)?$/i);
  if (!m) return { total: 1, rolls: [1], mod: 0 };
  const n = Math.max(1, parseInt(m[1] || "1", 10));
  const s = Math.max(2, parseInt(m[2], 10));
  const mod = m[3] ? parseInt(m[3], 10) : 0;
  const rolls = Array.from({ length: n }, () => Math.floor(Math.random() * s) + 1);
  return {
    total: Math.max(1, rolls.reduce((a, b) => a + b, 0) + mod),
    rolls,
    mod,
  };
}

export function DiceRollPrompt({
  request,
  onResult,
}: {
  request: DiceRequest;
  onResult: (spec: string, value: number, rolls: number[], reason: string) => void;
}) {
  const [spinning, setSpinning] = useState(false);
  const [result, setResult] = useState<{ total: number; rolls: number[] } | null>(null);
  const [manualValue, setManualValue] = useState("");

  const handleAutoRoll = () => {
    setSpinning(true);
    setTimeout(() => {
      const r = clientRollDice(request.spec);
      setResult(r);
      setSpinning(false);
    }, 580);
  };

  const handleSubmit = () => {
    if (result) {
      onResult(request.spec, result.total, result.rolls, request.reason);
    } else if (manualValue) {
      const v = parseInt(manualValue, 10);
      if (!isNaN(v)) onResult(request.spec, v, [], request.reason);
    }
  };

  const handleManual = () => {
    const v = parseInt(manualValue, 10);
    if (!isNaN(v)) onResult(request.spec, v, [], request.reason);
  };

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.97, y: 6 }}
      animate={{ opacity: 1, scale: 1, y: 0 }}
      exit={{ opacity: 0, scale: 0.95 }}
      transition={{ duration: 0.2 }}
      className="msg-dice-request px-4 py-3 space-y-3"
    >
      <div className="flex items-center gap-2">
        <Dices className="w-4 h-4 text-amber-400" />
        <span className="text-amber-300 text-xs font-semibold uppercase tracking-wider">
          Roll Required
        </span>
      </div>

      <div className="space-y-0.5">
        <p className="text-sm text-slate-200 font-medium">{request.reason}</p>
        <p className="text-xs font-mono text-amber-400">{request.spec}</p>
      </div>

      {result ? (
        <div className="space-y-2">
          <div className="flex flex-wrap items-center gap-1.5">
            {result.rolls.map((r, i) => (
              <span key={i} className="dice-face">
                {r}
              </span>
            ))}
            <span className="text-slate-500 text-xs mx-1">→</span>
            <span className="dice-face-total">{result.total}</span>
          </div>
          <button onClick={handleSubmit} className="btn-cyber text-xs px-3 py-1.5">
            Confirm {result.total} and continue
          </button>
        </div>
      ) : (
        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={handleAutoRoll}
            disabled={spinning}
            className="btn-cyber text-xs px-3 py-1.5 gap-1.5"
          >
            <Dices className={cn("w-3.5 h-3.5", spinning && "animate-dice-spin")} />
            {spinning ? "Rolling…" : `Roll ${request.spec}`}
          </button>
          <span className="text-slate-600 text-xs">or enter manually</span>
          <div className="flex items-center gap-1">
            <input
              type="number"
              min={1}
              value={manualValue}
              onChange={(e) => setManualValue(e.target.value)}
              placeholder="0"
              className="w-16 input-cyber text-xs py-1 px-2 text-center"
              onKeyDown={(e) => e.key === "Enter" && handleManual()}
            />
            <button
              onClick={handleManual}
              disabled={!manualValue}
              className="btn-ghost text-xs px-2 py-1"
            >
              Use
            </button>
          </div>
        </div>
      )}
    </motion.div>
  );
}