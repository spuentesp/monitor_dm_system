"use client";

import { useQuery } from "@tanstack/react-query";
import { AlertCircle, BookOpen, Loader2, RotateCcw } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { chatApi } from "@/lib/api";
import { DialogShell } from "@/components/DialogShell";
import { CopyButton } from "@/features/chat/CopyButton";
import { PLAY_KEYS } from "@/lib/query-keys";

/** Server-generated "story so far" prose recap for a chat session (T-068 / CF-2). */
export function RecapModal({ sessionId, onClose }: { sessionId: string; onClose: () => void }) {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: PLAY_KEYS.recap(sessionId),
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
                <CopyButton text={data.recap} className="flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-lg border border-white/10 text-slate-400 hover:text-slate-200 hover:bg-white/5 transition-all" />
              </div>
            )}
          </div>
        )}
      </div>
    </DialogShell>
  );
}
