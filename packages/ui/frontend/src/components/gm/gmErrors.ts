import { errorMessage } from "@/lib/errors";

/**
 * Copy for a 429 from the shared provider pool / usage cap (UX-4 §3):
 * quota errors must read as a limit the admin can raise, never a raw body.
 */
export const RATE_LIMIT_MESSAGE =
  "Daily limit reached - resets 00:00 UTC. Ask your admin to raise it.";

/**
 * True for ApiError(429). Checks the `status` shape instead of
 * `instanceof ApiError` so the helper keeps working when a test mocks
 * "@/lib/api" (and covers any ApiError-like object).
 */
export function isRateLimit(err: unknown): boolean {
  return (
    typeof err === "object" &&
    err !== null &&
    "status" in err &&
    (err as { status: unknown }).status === 429
  );
}

/**
 * Error copy for GM panel displays: 429 becomes the daily-limit message,
 * everything else keeps the panel's own fallback text.
 */
export function gmErrorMessage(err: unknown, fallback: string): string {
  return isRateLimit(err) ? RATE_LIMIT_MESSAGE : fallback;
}

/** Like gmErrorMessage, but falls back to the extracted error text. */
export function gmErrorText(err: unknown): string {
  return gmErrorMessage(err, errorMessage(err));
}
