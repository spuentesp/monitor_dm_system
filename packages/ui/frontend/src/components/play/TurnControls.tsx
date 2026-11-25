"use client";

import { Pencil, RotateCcw, Undo2 } from "lucide-react";

import type { Message } from "@/lib/types";

/**
 * The last player action the edit/regenerate controls operate on.
 *
 * Rewind excises the FINAL player message's exchange, so these controls
 * only surface when that final player message is a plain, non-empty action
 * (dice results and roll requests have their own flow — re-sending their
 * display text would lose the roll metadata). Returns null when there is
 * no player message at all or the final one is a dice/roll message.
 */
export function findLastPlayerAction(messages: Message[]): string | null {
  for (let i = messages.length - 1; i >= 0; i--) {
    const m = messages[i];
    if (m.role !== "player") continue;
    const type = (m.metadata as { type?: string } | undefined)?.type;
    if (type === "dice_result" || type === "roll_request") return null;
    const text = m.content.trim();
    return text || null;
  }
  return null;
}

/** True once the player has sent any message — gates the Undo control. */
export function hasPlayerMessage(messages: Message[]): boolean {
  return messages.some((m) => m.role === "player");
}

const CONTROL_CLASS =
  "flex items-center gap-1.5 rounded-lg border border-white/10 px-2.5 py-1.5 text-[11px] text-slate-400 transition-colors hover:border-cyan-500/30 hover:bg-cyan-500/10 hover:text-cyan-200 disabled:cursor-not-allowed disabled:opacity-40";

/**
 * Turn controls for the play console (UX-6 item 3) — all backed by
 * POST /chat/{id}/rewind:
 *
 * - **Undo** removes the last exchange (final player message + GM reply).
 * - **Edit last turn** rewinds, then hands the removed text to the caller
 *   to pre-fill the composer for an edited re-send.
 * - **Regenerate GM reply** rewinds, then re-sends the same text so the GM
 *   produces a fresh reply without duplicating the player message.
 *
 * Hidden while no player message exists (nothing to rewind); every control
 * is disabled while a turn is in flight.
 */
export function TurnControls({
  messages,
  disabled,
  onUndo,
  onEditLast,
  onRegenerate,
}: {
  messages: Message[];
  /** True while a turn is in flight — block the controls meanwhile. */
  disabled: boolean;
  /** Rewind and drop the last exchange from the local view. */
  onUndo: () => void;
  /** Rewind, then pre-fill the composer with the removed player text. */
  onEditLast: (text: string) => void;
  /** Rewind, then re-send the removed player text for a fresh GM reply. */
  onRegenerate: (text: string) => void;
}) {
  if (!hasPlayerMessage(messages)) return null;
  const lastAction = findLastPlayerAction(messages);

  return (
    <div className="flex items-center gap-2" data-testid="turn-controls">
      <button
        type="button"
        disabled={disabled}
        onClick={() => onUndo()}
        title="Remove your last action and the GM's reply"
        className={CONTROL_CLASS}
      >
        <Undo2 className="h-3 w-3" />
        Undo last turn
      </button>
      {lastAction && (
        <button
          type="button"
          disabled={disabled}
          onClick={() => onEditLast(lastAction)}
          title="Rewind your last action and edit it before re-sending"
          className={CONTROL_CLASS}
        >
          <Pencil className="h-3 w-3" />
          Edit last turn
        </button>
      )}
      {lastAction && (
        <button
          type="button"
          disabled={disabled}
          onClick={() => onRegenerate(lastAction)}
          title="Re-send your last action to get a fresh GM reply"
          className={CONTROL_CLASS}
        >
          <RotateCcw className="h-3 w-3" />
          Regenerate GM reply
        </button>
      )}
    </div>
  );
}
