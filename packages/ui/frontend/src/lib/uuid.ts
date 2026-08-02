/**
 * `crypto.randomUUID()` is only available in secure contexts (HTTPS or
 * localhost). Plain HTTP over a LAN IP is not a secure context, so phones
 * on `http://192.168.x.x:3000` hit `crypto.randomUUID is not a function`.
 *
 * This helper prefers the native API when present and falls back to a
 * `Math.random`-based UUIDv4 otherwise. The fallback is not
 * cryptographically strong, but it's good enough for client-side message
 * keys and a vast improvement over `Date.now()`-based ids.
 */
export function uuid(): string {
  const c = (typeof globalThis !== "undefined" ? globalThis : window).crypto;
  if (c && typeof c.randomUUID === "function") {
    return c.randomUUID();
  }
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (ch) => {
    const r = (Math.random() * 16) | 0;
    const v = ch === "x" ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}
