"use client";

import { useState } from "react";
import { Globe2, Loader2, Send } from "lucide-react";
import { searchApi } from "@/lib/api";
import type { SearchResultItem } from "@/lib/types";
import { errorMessage } from "@/lib/errors";
import { cn } from "@/lib/utils";

type QA = { question: string; results: SearchResultItem[]; error?: string };

/**
 * "Ask the world" — natural-language questions against the selected universe's
 * canon, backed by the existing scoped semantic-search endpoint.
 */
export function AskTheWorldPanel({ universeId }: { universeId: string | null }) {
  const [draft, setDraft] = useState("");
  const [asking, setAsking] = useState(false);
  const [history, setHistory] = useState<QA[]>([]);

  if (!universeId) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-2 p-6 text-center">
        <Globe2 className="h-8 w-8 text-slate-700" />
        <p className="text-xs text-slate-600">Select a universe to ask its canon questions</p>
      </div>
    );
  }

  async function ask() {
    const q = draft.trim();
    if (!q || asking || !universeId) return;
    setDraft("");
    setAsking(true);
    try {
      const res = await searchApi.universeSearch(universeId, q, { limit: 5 });
      setHistory((h) => [...h, { question: q, results: res.results }]);
    } catch (e) {
      setHistory((h) => [...h, { question: q, results: [], error: errorMessage(e) }]);
    } finally {
      setAsking(false);
    }
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex-1 space-y-4 overflow-y-auto p-3">
        {history.length === 0 && (
          <p className="p-2 text-center text-[11px] text-slate-600">
            Ask anything about this world — answers come from stored canon.
          </p>
        )}
        {history.map((qa, i) => (
          <div key={i} className="space-y-2">
            <div className="flex justify-end">
              <div className="max-w-[85%] rounded-2xl rounded-br-sm bg-emerald-500/15 px-3 py-1.5 text-xs text-slate-200">
                {qa.question}
              </div>
            </div>
            {qa.error ? (
              <div className="rounded-lg border border-red-500/20 bg-red-500/5 px-3 py-2 text-[11px] text-red-300">
                {qa.error}
              </div>
            ) : qa.results.length === 0 ? (
              <div className="px-2 text-[11px] text-slate-600">No canon found for that.</div>
            ) : (
              qa.results.map((r) => (
                <div key={r.id} className="glass rounded-xl px-3 py-2">
                  <div className="mb-1 flex items-center gap-2">
                    <span className="rounded border border-emerald-500/25 bg-emerald-500/10 px-1.5 py-0.5 text-[9px] text-emerald-300">
                      {r.collection}
                    </span>
                    {r.entity_type && (
                      <span className="text-[9px] text-slate-600">{r.entity_type}</span>
                    )}
                    <span className="ml-auto text-[9px] tabular-nums text-slate-600">
                      {r.score.toFixed(2)}
                    </span>
                  </div>
                  <p className="text-xs leading-relaxed text-slate-300">{r.text ?? "—"}</p>
                </div>
              ))
            )}
          </div>
        ))}
        {asking && (
          <div className="flex items-center gap-2 px-2 text-[11px] text-slate-600">
            <Loader2 className="h-3 w-3 animate-spin" /> Consulting canon…
          </div>
        )}
      </div>
      <div className="flex items-end gap-2 border-t border-white/5 p-3">
        <textarea
          className="input-cyber max-h-24 min-h-[38px] flex-1 resize-none text-xs"
          placeholder="Ask the world…"
          value={draft}
          rows={1}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void ask();
            }
          }}
        />
        <button
          onClick={() => void ask()}
          disabled={asking || !draft.trim()}
          className={cn("btn-cyber px-3 py-2", (asking || !draft.trim()) && "opacity-50")}
          title="Ask"
        >
          <Send className="h-3.5 w-3.5" />
          <span className="sr-only">Ask</span>
        </button>
      </div>
    </div>
  );
}
