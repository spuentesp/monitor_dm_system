"use client";

import { motion } from "framer-motion";
import { Flag } from "lucide-react";
import type { ConsequenceChoice } from "./types";

/** Surface a GM-offered consequence-choice prompt with up to 4 options. */
export function ConsequenceBanner({
  pending,
  disabled,
  onChoose,
}: {
  pending: ConsequenceChoice;
  disabled: boolean;
  onChoose: (option: string) => void;
}) {
  const options = Array.isArray(pending.options)
    ? pending.options.map(String).filter(Boolean)
    : [];
  if (options.length === 0) return null;
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      className="mb-3 rounded-xl border border-amber-500/30 bg-amber-500/8 px-4 py-3 space-y-2"
    >
      <div className="flex items-center gap-2 text-xs font-semibold text-amber-300 uppercase tracking-wider">
        <Flag className="w-3.5 h-3.5" />
        The cost comes due — choose
      </div>
      {typeof pending.risk_preview === "string" && pending.risk_preview && (
        <p className="text-xs text-amber-100/80 leading-relaxed">{pending.risk_preview}</p>
      )}
      <div className="flex flex-col gap-1.5">
        {options.slice(0, 4).map((opt) => (
          <button
            key={opt}
            onClick={() => onChoose(opt)}
            disabled={disabled}
            className="text-left text-xs px-3 py-2 rounded-lg border border-amber-500/25 text-amber-50 hover:bg-amber-500/15 disabled:opacity-50 transition-all"
          >
            {opt}
          </button>
        ))}
      </div>
    </motion.div>
  );
}