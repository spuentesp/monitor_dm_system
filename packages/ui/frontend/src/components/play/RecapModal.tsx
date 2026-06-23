"use client";

import { useQuery } from "@tanstack/react-query";
import { AlertCircle, BookOpen, Check, Copy, Loader2, RotateCcw } from "lucide-react";
import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { chatApi } from "@/lib/api";
import { DialogShell } from "@/components/DialogShell";
import { cn } from "@/lib/utils";

function RecapCopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      onClick={() =>
        navigator.clipboard?.writeText(text).then(() => {
          setCopied(true);
          setTimeout(() => setCopied(false), 1500);
        })
      }
      className={cn(
        "flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-lg border border-white/10",
        "text-slate-400 hover:text-slate-200 hover:bg-white/5 transition-all",
      )}
    >
      {copied ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
      {copied ? "Copied" : "Copy"}
    </button>
  );
}

/** Server-generated "story so far" prose recap for a chat session (T-068 / CF-2). */
export function RecapModal({ sessionId, onClose }: { sessionId: string; onClose: () => void }) {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["session-recap", sessionId],
    queryFn: () => chatApi.getRecap(sessionId),
    staleTime: 60_000,
    retry: false,
  });

  return (
    <DialogShell
      title="The story so far"
      icon={BookOpen}
      iconClassName="text-amber-400"
      onClose={onClose}
      maxWidthClassName="max-w-2xl"
    >
      <div className="p-5 max-h-[60vh] overflow-y-auto">
        {isLoading ? (
          <div className="flex items-center gap-3 py-10 justify-center text-slate-500">
            <Loader2 className="w-5 h-5 animate-spin" />
            <span className="text-sm">The chronicler is gathering the threads…</span>
          </div>
        ) : error ? (
          <div className="flex flex-col items-center gap-3 py-8 text-center">
            <AlertCircle className="w-8 h-8 text-red-500/60" />
            <p className="text-sm text-slate-400">Couldn&apos;t build the recap.</p>
            <button onClick={() => refetch()} className="btn-cyber text-xs">
              <RotateCcw className="w-3.5 h-3.5" /> Try again
            </button>
          </div>
        ) : (
          <div className="space-y-3">
            <div className="prose-bubble text-sm text-slate-300 leading-relaxed">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {data?.recap || "Nothing has happened yet — the page is blank."}
              </ReactMarkdown>
            </div>
            {data?.recap && (
              <div className="flex justify-end">
                <RecapCopyButton text={data.recap} />
              </div>
            )}
          </div>
        )}
      </div>
    </DialogShell>
  );
}
