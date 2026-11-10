"use client";

import { useState } from "react";
import { AlertTriangle, CheckCircle2, FileText, Loader2, Scroll } from "lucide-react";
import { useMutation } from "@tanstack/react-query";
import { gmTableApi } from "@/lib/gm-table-api";
import type { SessionLogProposeResponse } from "@/lib/gm-table-types";
import { cn } from "@/lib/utils";

/**
 * Session log → canon (Phase 7 Part B, CF-5/CF-8): after the session, the GM
 * types or pastes what happened; the assistant stages canon changes for the
 * CF-8 review queue and flags contradictions with existing canon (direct +
 * G-9 implication depth).
 */
export function SessionLogPanel({ universeId }: { universeId: string | null }) {
  const [logText, setLogText] = useState("");
  const [result, setResult] = useState<SessionLogProposeResponse | null>(null);

  const propose = useMutation({
    mutationFn: () =>
      gmTableApi.proposeSessionLog({ universe_id: universeId!, log_text: logText }),
    onSuccess: setResult,
  });

  if (!universeId) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-center space-y-2 px-4">
        <FileText className="w-8 h-8 text-slate-700" />
        <p className="text-xs text-slate-600">Select a universe to log what happened</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <div className="flex items-center gap-2 px-4 py-3 border-b border-white/5 flex-shrink-0">
        <FileText className="w-3.5 h-3.5 text-emerald-400" />
        <span className="text-xs font-semibold text-slate-300 flex-1">Session Log → Canon</span>
        <button
          onClick={() => propose.mutate()}
          disabled={!logText.trim() || propose.isPending}
          className={cn("btn-cyber text-xs py-1 px-3", !logText.trim() && "opacity-40 cursor-not-allowed")}
        >
          {propose.isPending ? <Loader2 className="w-3 h-3 animate-spin" /> : <Scroll className="w-3 h-3" />}
          Propose canon changes
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
        <textarea
          value={logText}
          onChange={(e) => setLogText(e.target.value)}
          placeholder={[
            "Paste or type what happened tonight…",
            "",
            "Example:",
            "The party returned to Ironwatch at dusk. Mira confronted the guild",
            "master in the market and took back the key. The docks burned.",
          ].join("\n")}
          className="input-cyber w-full h-32 resize-none text-xs font-mono leading-relaxed"
          spellCheck={false}
        />
        {propose.isError && (
          <p className="text-[10px] text-red-400">
            Analysis failed — nothing was staged, try again.
          </p>
        )}

        {result && (
          <div className="space-y-2">
            <p className="text-[10px] text-slate-500">
              {result.items.length} proposed change(s) staged for review in the Canon Review
              queue (batch {result.batch_id.slice(0, 8)}).
            </p>
            {result.items.map((item, i) => (
              <div
                key={i}
                className={cn(
                  "glass-dark rounded-xl border p-2.5 space-y-1",
                  item.flags.length > 0 ? "border-amber-500/30" : "border-white/5",
                )}
              >
                <div className="flex items-start gap-2">
                  {item.flags.length > 0 ? (
                    <AlertTriangle className="w-3.5 h-3.5 text-amber-400 flex-shrink-0 mt-0.5" />
                  ) : (
                    <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 flex-shrink-0 mt-0.5" />
                  )}
                  <p className="text-xs text-slate-200 leading-relaxed">{item.statement}</p>
                </div>
                {(item.participants.length > 0 || item.locations.length > 0) && (
                  <div className="flex flex-wrap gap-1">
                    {item.participants.map((p) => (
                      <span key={`p-${p}`} className="text-[9px] bg-purple-500/10 text-purple-300 px-1.5 py-0.5 rounded">
                        {p}
                      </span>
                    ))}
                    {item.locations.map((l) => (
                      <span key={`l-${l}`} className="text-[9px] bg-cyan-500/10 text-cyan-300 px-1.5 py-0.5 rounded">
                        {l}
                      </span>
                    ))}
                  </div>
                )}
                {item.flags.map((f, j) => (
                  <p key={j} className="text-[10px] text-amber-300/90">
                    [{f.kind} · {f.severity}] {f.explanation}
                  </p>
                ))}
                {item.proposal_id && (
                  <p className="text-[9px] text-slate-600">proposal {item.proposal_id.slice(0, 8)}</p>
                )}
              </div>
            ))}
            {result.proposal_errors.length > 0 && (
              <div>
                <h4 className="text-[9px] font-bold tracking-widest uppercase text-red-400 mb-1">
                  Not staged
                </h4>
                {result.proposal_errors.map((e, i) => (
                  <p key={i} className="text-[10px] text-red-300/80">{e}</p>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
