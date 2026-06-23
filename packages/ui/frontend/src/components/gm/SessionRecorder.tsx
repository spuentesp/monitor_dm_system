"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { motion } from "framer-motion";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertCircle,
  BookOpen,
  Bot,
  CircleDot,
  Flag,
  GitBranch,
  Loader2,
  Mic,
  Plus,
  Send,
  ShieldCheck,
  User,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { chatApi, storiesApi } from "@/lib/api";
import type { Message, Session, StoryThread } from "@/lib/types";
import { cn, formatRelativeTime } from "@/lib/utils";
import { RecapModal } from "@/components/play/RecapModal";
import { CanonReviewPanel } from "@/components/canon/CanonReviewPanel";

/**
 * CF-1 Session Recorder — capture what happened at the (human-run) table.
 *
 * Each recording is a `gm_assistant` chat session bound to the universe; the
 * backend auto-creates a capture story + scene ("Human-led session capture and
 * review"). Logged entries become turns, the co-pilot reflects back insights,
 * and "Close session" runs scene-end so everything lands in the canon review
 * queue (CF-8).
 */
export function SessionRecorder({
  universeId,
  universeLabel,
}: {
  universeId: string;
  universeLabel?: string | null;
}) {
  const qc = useQueryClient();
  const [activeId, setActiveId] = useState<string | null>(null);
  const [entry, setEntry] = useState("");
  const [waiting, setWaiting] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const [showRecap, setShowRecap] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);

  const { data: allSessions = [], isLoading: sessionsLoading } = useQuery({
    queryKey: ["sessions"],
    queryFn: () => chatApi.listSessions(),
  });

  const recordings = useMemo(
    () =>
      allSessions
        .filter((s: Session) => s.mode === "gm_assistant" && s.universe_id === universeId)
        .sort((a, b) => (b.updated_at ?? "").localeCompare(a.updated_at ?? "")),
    [allSessions, universeId],
  );

  // Pick the latest recording for this universe by default
  useEffect(() => {
    if (activeId && recordings.some((r) => r.id === activeId)) return;
    setActiveId(recordings[0]?.id ?? null);
  }, [recordings, activeId]);

  const active = recordings.find((r) => r.id === activeId) ?? null;

  const { data: messages = [] } = useQuery({
    queryKey: ["chat", activeId, "messages"],
    queryFn: () => chatApi.getMessages(activeId!),
    enabled: !!activeId,
  });

  const { data: threads = [] } = useQuery({
    queryKey: ["story-threads", active?.story_id],
    queryFn: () => storiesApi.listThreads(active!.story_id!),
    enabled: !!active?.story_id,
    staleTime: 30_000,
    retry: 1,
  });

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length, waiting]);

  const createRecording = useMutation({
    mutationFn: () =>
      chatApi.createSession({
        title: `Table log — ${new Date().toLocaleDateString()}`,
        mode: "gm_assistant",
        universe_id: universeId,
        universe_label: universeLabel ?? undefined,
        tone: "dramatic",
      }),
    onSuccess: (s) => {
      qc.invalidateQueries({ queryKey: ["sessions"] });
      setActiveId(s.id);
    },
  });

  const logEntry = () => {
    const text = entry.trim();
    if (!text || !activeId || waiting) return;
    setEntry("");
    setFailure(null);
    setWaiting(true);

    const optimistic: Message = {
      id: crypto.randomUUID(),
      session_id: activeId,
      role: "player",
      content: text,
      timestamp: new Date().toISOString(),
      metadata: {},
    };
    qc.setQueryData<Message[]>(["chat", activeId, "messages"], (prev) => [
      ...(prev ?? []),
      optimistic,
    ]);

    chatApi
      .sendMessage(activeId, text)
      .then(() => {
        qc.invalidateQueries({ queryKey: ["chat", activeId, "messages"] });
        qc.invalidateQueries({ queryKey: ["sessions"] });
      })
      .catch((err: unknown) => {
        setFailure(err instanceof Error ? err.message : "Logging failed");
      })
      .finally(() => setWaiting(false));
  };

  const [closing, setClosing] = useState(false);
  const closeSession = () => {
    if (!activeId || closing) return;
    setClosing(true);
    chatApi
      .endScene(activeId)
      .then(() => {
        qc.invalidateQueries({ queryKey: ["chat", activeId, "messages"] });
        qc.invalidateQueries({ queryKey: ["sessions"] });
      })
      .catch((err: unknown) => {
        setFailure(err instanceof Error ? err.message : "Scene wrap-up failed");
      })
      .finally(() => setClosing(false));
  };

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Toolbar */}
      <div className="flex items-center gap-2 px-4 py-2 border-b border-white/5 flex-shrink-0">
        <Mic className="w-3.5 h-3.5 text-red-400" />
        <span className="text-[10px] font-bold tracking-widest uppercase text-slate-600">
          Session Recorder
        </span>
        <select
          value={activeId ?? ""}
          onChange={(e) => setActiveId(e.target.value || null)}
          className="input-cyber py-0.5 text-xs min-w-[160px] ml-2"
          disabled={recordings.length === 0}
        >
          {recordings.length === 0 && <option value="">No recordings yet</option>}
          {recordings.map((r) => (
            <option key={r.id} value={r.id}>
              {r.title} · {formatRelativeTime(r.updated_at)}
            </option>
          ))}
        </select>
        <div className="flex-1" />
        <button
          onClick={() => createRecording.mutate()}
          disabled={createRecording.isPending}
          className="btn-cyber text-xs py-1 px-2.5"
          title="Start a new capture session for this universe"
        >
          {createRecording.isPending ? (
            <Loader2 className="w-3 h-3 animate-spin" />
          ) : (
            <Plus className="w-3 h-3" />
          )}
          New recording
        </button>
        {active && (
          <>
            <button
              onClick={() => setShowRecap(true)}
              className="btn-ghost text-xs py-1 px-2.5 border border-white/10"
              title="Generate a recap of everything logged (CF-2)"
            >
              <BookOpen className="w-3 h-3" /> Recap
            </button>
            <button
              onClick={closeSession}
              disabled={closing}
              className="btn-ghost text-xs py-1 px-2.5 border border-amber-500/25 text-amber-300"
              title="Close the capture scene and queue changes for canon review (CF-8)"
            >
              {closing ? <Loader2 className="w-3 h-3 animate-spin" /> : <Flag className="w-3 h-3" />}
              Close session
            </button>
          </>
        )}
      </div>

      {/* Body */}
      {sessionsLoading ? (
        <div className="flex-1 flex items-center justify-center text-slate-600">
          <Loader2 className="w-5 h-5 animate-spin" />
        </div>
      ) : !active ? (
        <div className="flex-1 flex flex-col items-center justify-center text-center px-8 space-y-3">
          <div className="w-14 h-14 rounded-2xl bg-red-500/8 border border-red-500/20 flex items-center justify-center">
            <Mic className="w-6 h-6 text-red-400/70" />
          </div>
          <p className="text-sm font-medium text-slate-300">Record your table session</p>
          <p className="text-xs text-slate-600 max-w-sm leading-relaxed">
            Log what happens as you run the game — events, NPC dialogue, player decisions. MONITOR
            keeps the transcript, reflects insights back, and queues every world change for canon
            review when you close the session.
          </p>
          <button onClick={() => createRecording.mutate()} className="btn-cyber text-xs mt-1">
            <CircleDot className="w-3.5 h-3.5 text-red-400" /> Start recording
          </button>
        </div>
      ) : (
        <>
          {/* Transcript */}
          <div className="flex-1 overflow-y-auto px-4 py-3 space-y-2.5">
            {messages.map((m) => {
              const isGM = m.role === "gm";
              return (
                <motion.div
                  key={m.id}
                  initial={{ opacity: 0, y: 4 }}
                  animate={{ opacity: 1, y: 0 }}
                  className={cn(
                    "rounded-xl border px-3 py-2 text-xs leading-relaxed",
                    isGM
                      ? "bg-emerald-500/4 border-emerald-500/15 text-slate-400"
                      : "bg-white/4 border-white/8 text-slate-200",
                  )}
                >
                  <div
                    className={cn(
                      "flex items-center gap-1.5 text-[10px] font-semibold mb-1",
                      isGM ? "text-emerald-400" : "text-slate-500",
                    )}
                  >
                    {isGM ? <Bot className="w-3 h-3" /> : <User className="w-3 h-3" />}
                    {isGM ? "Co-pilot" : "Logged"}
                    <span className="font-normal text-slate-600 ml-auto">
                      {formatRelativeTime(m.timestamp)}
                    </span>
                  </div>
                  <div className="prose-bubble">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>{m.content}</ReactMarkdown>
                  </div>
                </motion.div>
              );
            })}
            {waiting && (
              <div className="flex items-center gap-2 text-[11px] text-slate-600 px-1">
                <Loader2 className="w-3 h-3 animate-spin" /> co-pilot is reading…
              </div>
            )}
            {failure && (
              <div className="rounded-xl border border-red-500/25 bg-red-500/5 px-3 py-2 text-xs text-red-300 flex items-center gap-2">
                <AlertCircle className="w-3.5 h-3.5 flex-shrink-0" /> {failure}
              </div>
            )}
            <div ref={endRef} />
          </div>

          {/* Open threads strip */}
          {threads.length > 0 && (
            <div className="px-4 py-2 border-t border-white/5 flex-shrink-0">
              <div className="flex items-center gap-1.5 text-[10px] text-slate-600 uppercase tracking-wider mb-1.5">
                <GitBranch className="w-3 h-3" /> Open threads
              </div>
              <div className="flex flex-wrap gap-1.5">
                {threads.slice(0, 5).map((t: StoryThread, i) => (
                  <span
                    key={t.id ?? `${t.title}-${i}`}
                    className="text-[10px] px-2 py-0.5 rounded-full border border-purple-500/20 bg-purple-500/5 text-purple-300"
                  >
                    {t.title}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Canon review for the capture story */}
          {active.story_id && (
            <div className="px-4 py-2 border-t border-white/5 flex-shrink-0 max-h-56 overflow-y-auto">
              <div className="flex items-center gap-1.5 text-[10px] text-slate-600 uppercase tracking-wider mb-1.5">
                <ShieldCheck className="w-3 h-3" /> Canon review
              </div>
              <CanonReviewPanel storyId={active.story_id} compact />
            </div>
          )}

          {/* Log composer */}
          <div className="px-4 py-3 border-t border-white/5 flex-shrink-0">
            <div className="flex items-end gap-2 glass rounded-xl p-2.5">
              <textarea
                value={entry}
                onChange={(e) => setEntry(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    logEntry();
                  }
                }}
                placeholder="Log what happened — “The party found the sealed door beneath the chapel; Mira pocketed the key without telling anyone.”"
                rows={2}
                className="flex-1 bg-transparent text-xs text-slate-200 placeholder:text-slate-600 resize-none focus:outline-none"
              />
              <button
                onClick={logEntry}
                disabled={!entry.trim() || waiting}
                className={cn(
                  "flex-shrink-0 w-8 h-8 rounded-lg flex items-center justify-center transition-all",
                  entry.trim() && !waiting
                    ? "bg-emerald-500/15 text-emerald-400 border border-emerald-500/30 hover:bg-emerald-500/25"
                    : "bg-white/4 text-slate-600 border border-white/8 cursor-not-allowed",
                )}
              >
                <Send className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        </>
      )}

      {showRecap && activeId && (
        <RecapModal sessionId={activeId} onClose={() => setShowRecap(false)} />
      )}
    </div>
  );
}
