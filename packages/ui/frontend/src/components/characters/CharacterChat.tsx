"use client";

import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ArrowLeft, Send, Heart, ShieldAlert, Sparkles, ImagePlus, Loader2 } from "lucide-react";
import { entitiesApi, imageApi } from "@/lib/api";
import type { StandaloneCharacter } from "@/lib/types";
import { useNotify } from "@/components/NotificationProvider";
import { cn } from "@/lib/utils";
import { errorMessage } from "@/lib/errors";

type ChatMessage = {
  id: string;
  role: "user" | "char";
  text: string;
  emotional_state?: string | null;
  snapshot?: Record<string, unknown>;
  image_url?: string;
};

function num(snapshot: Record<string, unknown> | undefined, key: string): number {
  const v = snapshot?.[key];
  return typeof v === "number" ? v : 0;
}

/** Story-less conversatory with a single MONITOR-backed character. */
export function CharacterChat({
  character,
  onBack,
}: {
  character: StandaloneCharacter;
  onBack: () => void;
}) {
  const { notify } = useNotify();
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [starting, setStarting] = useState(true);
  const [sending, setSending] = useState(false);
  const [sceneBusy, setSceneBusy] = useState(false);
  // Character Versions: broaden memory recall to other universes of this
  // character when the user opts in (default off — strict universe scope).
  const [includeCrossIncarnation, setIncludeCrossIncarnation] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const convRef = useRef<string | null>(null);

  // Open a session on mount; end it on unmount (best-effort).
  useEffect(() => {
    let active = true;
    setStarting(true);
    entitiesApi
      .startCharacterConversation(character.id)
      .then((res) => {
        if (!active) return;
        convRef.current = res.conversation_id;
        setConversationId(res.conversation_id);
        setMessages([{ id: "opening", role: "char", text: res.opening }]);
      })
      .catch((e) => active && notify("error", `Couldn't start chat: ${errorMessage(e)}`))
      .finally(() => active && setStarting(false));
    return () => {
      active = false;
      const cid = convRef.current;
      if (cid) entitiesApi.endCharacterConversation(character.id, cid).catch(() => {});
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [character.id]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, sending]);

  const lastRead = [...messages].reverse().find((m) => m.role === "char" && m.snapshot);

  async function send() {
    const text = draft.trim();
    if (!text || !conversationId || sending) return;
    setDraft("");
    setMessages((m) => [...m, { id: `u-${Date.now()}`, role: "user", text }]);
    setSending(true);
    try {
      const reply = await entitiesApi.sendCharacterMessage(
        character.id,
        conversationId,
        text,
        { include_cross_incarnation: includeCrossIncarnation },
      );
      setMessages((m) => [
        ...m,
        {
          id: `c-${Date.now()}`,
          role: "char",
          text: reply.text || "…",
          emotional_state: reply.emotional_state,
          snapshot: reply.relationship_snapshot,
        },
      ]);
    } catch (e) {
      notify("error", `Reply failed: ${errorMessage(e)}`);
    } finally {
      setSending(false);
    }
  }

  /** Summarise the recent chat into a scene illustration (never blocks chat). */
  async function generateScene() {
    if (!conversationId || sceneBusy) return;
    setSceneBusy(true);
    try {
      const res = await imageApi.generateScene({ conversation_id: conversationId, last_n: 12 });
      setMessages((m) => [
        ...m,
        { id: `img-${Date.now()}`, role: "char", text: "", image_url: res.image_url },
      ]);
    } catch (e) {
      notify("error", `Scene image failed: ${errorMessage(e)}`);
    } finally {
      setSceneBusy(false);
    }
  }

  const stance = (lastRead?.snapshot?.["stance"] as string) ?? "neutral";

  return (
    <div className="flex h-full min-h-0">
      {/* Conversation column */}
      <div className="flex flex-1 flex-col min-h-0">
        <div className="flex items-center gap-3 border-b border-border p-3">
          <button className="btn-ghost p-1.5" onClick={onBack} title="Back to roster">
            <ArrowLeft className="h-4 w-4" />
          </button>
          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-accent-primary/15 text-accent-primary text-xs font-bold">
            {character.name.slice(0, 2).toUpperCase()}
          </div>
          <div className="min-w-0">
            <div className="truncate text-sm font-semibold text-fg-primary">{character.name}</div>
            <div className="truncate text-xs text-fg-muted">{character.description || "Conversatory"}</div>
          </div>
          <button
            className="btn-ghost ml-auto p-1.5"
            onClick={() => void generateScene()}
            disabled={!conversationId || sceneBusy}
            aria-label="Generate scene image"
            title="🖼 Generate scene image from the recent chat"
          >
            {sceneBusy ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <ImagePlus className="h-4 w-4" />
            )}
          </button>
        </div>

        <div ref={scrollRef} className="flex-1 space-y-3 overflow-y-auto p-4">
          {starting && <div className="text-center text-xs text-fg-muted">Opening conversation…</div>}
          <AnimatePresence initial={false}>
            {messages.map((m) => (
              <motion.div
                key={m.id}
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                className={cn("flex", m.role === "user" ? "justify-end" : "justify-start")}
              >
                <div
                  className={cn(
                    "max-w-[78%] rounded-2xl px-3.5 py-2 text-sm leading-relaxed whitespace-pre-wrap",
                    m.role === "user"
                      ? "bg-accent-primary/20 text-fg-primary rounded-br-sm"
                      : "glass text-fg-secondary rounded-bl-sm",
                  )}
                >
                  {m.image_url && (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={m.image_url}
                      alt="Scene illustration"
                      className="mb-1 max-w-full rounded-lg"
                    />
                  )}
                  {m.text}
                  {m.role === "char" && m.emotional_state && (
                    <div className="mt-1 text-[10px] uppercase tracking-wide text-fg-dim">
                      {m.emotional_state}
                    </div>
                  )}
                </div>
              </motion.div>
            ))}
          </AnimatePresence>
          {sending && (
            <div className="flex justify-start">
              <div className="glass flex items-center gap-1 rounded-2xl rounded-bl-sm px-4 py-3">
                <span className="typing-dot h-1.5 w-1.5 rounded-full bg-fg-muted" />
                <span className="typing-dot h-1.5 w-1.5 rounded-full bg-fg-muted" />
                <span className="typing-dot h-1.5 w-1.5 rounded-full bg-fg-muted" />
              </div>
            </div>
          )}
        </div>

        <div className="flex flex-col gap-2 border-t border-border p-3">
          <label className="flex items-center gap-2 text-[11px] text-fg-muted">
            <input
              type="checkbox"
              checked={includeCrossIncarnation}
              onChange={(e) => setIncludeCrossIncarnation(e.target.checked)}
              className="h-3 w-3 accent-accent-primary"
            />
            Remember across incarnations
            <span className="text-fg-dim">
              (broadens memory recall to other universes of this character)
            </span>
          </label>
          <div className="flex items-end gap-2">
            <textarea
              className="input-cyber max-h-32 min-h-[42px] flex-1 resize-none"
              placeholder={`Message ${character.name}…`}
              value={draft}
              rows={1}
              disabled={starting || !conversationId}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  send();
                }
              }}
            />
            <button
              className="btn-cyber px-3 py-2.5"
              onClick={send}
              disabled={sending || starting || !draft.trim()}
              title="Send"
            >
              <Send className="h-4 w-4" />
            </button>
          </div>
        </div>
      </div>

      {/* Live state side panel */}
      <aside className="hidden w-60 shrink-0 border-l border-border p-4 lg:block">
        <div className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-fg-muted">
          <Sparkles className="h-3.5 w-3.5 text-accent-primary" /> Live read
        </div>
        <div className="space-y-3 text-sm">
          <div>
            <div className="text-xs text-fg-dim">Emotional state</div>
            <div className="text-fg-primary">{lastRead?.emotional_state ?? "—"}</div>
          </div>
          <div>
            <div className="text-xs text-fg-dim">Stance toward you</div>
            <div className="font-medium capitalize text-fg-primary">{stance}</div>
          </div>
          <Meter icon={Heart} label="Trust" value={num(lastRead?.snapshot, "trust")} />
          <Meter icon={Heart} label="Affinity" value={num(lastRead?.snapshot, "affinity")} />
          <Meter icon={ShieldAlert} label="Fear" value={num(lastRead?.snapshot, "fear")} />
          <Meter icon={Sparkles} label="Familiarity" value={num(lastRead?.snapshot, "familiarity")} />
        </div>
        {!character.entity_id && (
          <p className="mt-4 text-xs text-fg-dim">
            This character will be expanded into a full MONITOR profile when you start chatting.
          </p>
        )}
      </aside>
    </div>
  );
}

function Meter({
  icon: Icon,
  label,
  value,
}: {
  icon: React.ElementType;
  label: string;
  value: number;
}) {
  const pct = Math.round(((value + 1) / 2) * 100); // -1..1 → 0..100
  return (
    <div>
      <div className="mb-1 flex items-center justify-between text-xs text-fg-dim">
        <span className="flex items-center gap-1">
          <Icon className="h-3 w-3" /> {label}
        </span>
        <span className="tabular-nums">{value >= 0 ? "+" : ""}{value.toFixed(2)}</span>
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-bg-base">
        <div
          className={cn("h-full rounded-full", value < 0 ? "bg-red-400/70" : "bg-accent-primary")}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}
