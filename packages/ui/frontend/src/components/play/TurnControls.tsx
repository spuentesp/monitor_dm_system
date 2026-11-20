"use client";

import { RotateCcw } from "lucide-react";

import type { Message } from "@/lib/types";

/**
 * The last player action (excluding dice results) — the message a
 * "regenerate" re-sends to get a fresh GM reply.
 *
 * Edit-last-turn and Undo are deliberately NOT rendered: the chat backend
 * exposes no message-edit / message-delete / undo endpoint (routers/chat.py
 * only has send/state/messages/recap/wrap-up/greet/begin/end-scene/
 * skip-preplay/PATCH-session/DELETE-session), so those controls would need
 * new backend work. Regenerate maps onto the existing POST /chat/{id}/send.
 */
export function findLastPlayerAction(messages: Message[]): string | null {
  for (let i = messages.length - 1; i >= 0; i--) {
    const m = messages[i];
    if (m.role !== "player") continue;
    if ((m.metadata as { type?: string } | undefined)?.type === "dice_result") continue;
    const text = m.content.trim();
    if (text) return text;
  }
  return null;
}

/**
 * Turn controls for the play console (UX-6). Currently: Regenerate only —
 * re-sends the last player action through the existing send endpoint so the
 * GM produces a new reply. Hidden while no player action exists or a turn
 * is already in flight.
 */
export function TurnControls({
  messages,
  disabled,
  onRegenerate,
}: {
  messages: Message[];
  /** True while a turn is in flight — block regeneration meanwhile. */
  disabled: boolean;
  onRegenerate: (text: string) => void;
}) {
  const lastAction = findLastPlayerAction(messages);
  if (!lastAction) return null;

  return (
    <div className="flex items-center gap-2" data-testid="turn-controls">
      <button
        type="button"
        disabled={disabled}
        onClick={() => onRegenerate(lastAction)}
        title="Re-send your last action to get a fresh GM reply"
        className="flex items-center gap-1.5 rounded-lg border border-white/10 px-2.5 py-1.5 text-[11px] text-slate-400 transition-colors hover:border-cyan-500/30 hover:bg-cyan-500/10 hover:text-cyan-200 disabled:cursor-not-allowed disabled:opacity-40"
      >
        <RotateCcw className="h-3 w-3" />
        Regenerate GM reply
      </button>
      {/* Edit last player turn / Undo: hidden — no backend endpoint exists. */}
    </div>
  );
}
