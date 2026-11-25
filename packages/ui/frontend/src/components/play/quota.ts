import { ApiError } from "@/lib/api";
import type { TurnFailure } from "@/features/chat";

/** UX-4 / UX-6: friendly copy for a hit usage cap (HTTP 429). */
export const QUOTA_MESSAGE =
  "Daily limit reached - resets 00:00 UTC. Ask your admin to raise it.";

/** True when an thrown error is an HTTP 429 from the API layer. */
export function isQuotaError(err: unknown): boolean {
  return err instanceof ApiError && err.status === 429;
}

/** Friendly quota copy for a caught error, or null when it isn't a 429. */
export function quotaMessageFor(err: unknown): string | null {
  return isQuotaError(err) ? QUOTA_MESSAGE : null;
}

/**
 * Detect a quota hit from raw response-body text. useChatSession's turn
 * failures only keep `ApiError.message` (the body), not the status, so the
 * failure card has to recognise 429s textually.
 */
const QUOTA_DETAIL_PATTERN =
  /(^|[^\d])429([^\d]|$)|\bquota\b|daily limit|rate[ -]?limit|usage limit/i;

export function isQuotaDetail(detail: string): boolean {
  return QUOTA_DETAIL_PATTERN.test(detail);
}

/**
 * Rewrite a turn-failure card's detail to the friendly quota copy when the
 * failure was a 429; pass every other failure through untouched.
 */
export function friendlyTurnFailure(failure: TurnFailure | null): TurnFailure | null {
  if (!failure) return null;
  if (isQuotaDetail(failure.detail)) {
    return { ...failure, detail: QUOTA_MESSAGE };
  }
  return failure;
}
