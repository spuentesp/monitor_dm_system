// Small utility for extracting a human-readable message from an unknown
// error value. React Query callbacks (onError) and try/catch blocks all
// receive `unknown` in our codebase; this gives them one canonical way to
// pull a string out without sprinkling `as any` casts everywhere.

/**
 * Return a human-readable string for an unknown thrown value.
 *
 * Handles the common shapes we see:
 *  - Error / DOMException: use `.message`
 *  - string: return as-is
 *  - { message: string }: use `.message`
 *  - anything else: stringify
 *
 * Accepts `unknown` so callers can pass a caught exception directly:
 *   try { ... } catch (e) { notify("error", errorMessage(e)); }
 */
export function errorMessage(err: unknown): string {
  if (typeof err === "string") return err;
  if (err == null) return String(err);
  if (typeof err === "object" && "message" in err) {
    const m = (err as { message?: unknown }).message;
    if (typeof m === "string" && m.length > 0) return m;
  }
  if (err instanceof Error) return err.message;
  try {
    return JSON.stringify(err);
  } catch {
    return String(err);
  }
}
