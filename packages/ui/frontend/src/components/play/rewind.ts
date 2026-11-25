// UX-6 turn controls: shared rewind flow for Undo, Edit-last-turn and
// Regenerate. All three call POST /chat/{id}/rewind; edit and regenerate
// then re-use the server-returned last_player_text, so the player message
// is never duplicated in the transcript.

import { ApiError } from "@/lib/api";
import { errorMessage } from "@/lib/errors";
import type { Message, RewindResult } from "@/lib/types";

/** Fallback copy when a rewind refusal carries no readable detail. */
export const REWIND_FAILED_MESSAGE = "Couldn't rewind the last turn.";

/**
 * Remove the last exchange (`removed` messages) from a local transcript copy.
 * Clamped so a stale/oversized count can never produce a negative slice.
 */
export function removeLastExchange(messages: Message[], removed: number): Message[] {
  if (!Number.isFinite(removed) || removed <= 0) return messages;
  return messages.slice(0, Math.max(0, messages.length - Math.floor(removed)));
}

/**
 * Human-readable message for a failed rewind.
 *
 * The backend refuses with readable `detail` strings — notably the 409
 * "canon already changed" refusal and the 409 turn-in-flight guard — so the
 * JSON body is parsed first; anything else falls back to `errorMessage`.
 */
export function rewindErrorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    try {
      const detail = (JSON.parse(err.message) as { detail?: unknown }).detail;
      if (typeof detail === "string" && detail.trim()) return detail;
    } catch {
      // non-JSON body — fall through to the generic message
    }
    if (err.status === 409) return REWIND_FAILED_MESSAGE;
  }
  const message = errorMessage(err);
  return message.trim() ? message : REWIND_FAILED_MESSAGE;
}

export interface RewindDeps {
  /** True while a turn is in flight — the control must not fire at all. */
  disabled: boolean;
  /** chatApi.rewind bound to the active session. */
  rewind: () => Promise<RewindResult>;
  /** Apply the successful result (remove the exchange from the local view). */
  onSuccess: (result: RewindResult) => void;
  /** Surface a failure (notify / failure card). */
  onError: (message: string) => void;
}

/**
 * Run the rewind step shared by all three controls. Returns the removed
 * player text on success (what edit/regenerate re-send), `null` on refusal
 * or when disabled — callers must do nothing further on `null`.
 */
export async function rewindLastExchange(deps: RewindDeps): Promise<string | null> {
  if (deps.disabled) return null;
  try {
    const result = await deps.rewind();
    deps.onSuccess(result);
    return result.last_player_text;
  } catch (err) {
    deps.onError(rewindErrorMessage(err));
    return null;
  }
}
