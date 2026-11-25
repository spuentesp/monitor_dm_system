// Shared helpers for the auth surfaces (login, forgot/reset password).
// Kept in lib so login/forgot/reset pages report auth failures identically
// and the rules are unit-testable without rendering a page.

import { ApiError } from "./api";

export type AuthFormMode = "login" | "signup" | "forgot" | "reset";

export type SignUpField = "email" | "username" | "password" | "invite" | "display_name";

export type AuthFieldErrors = Partial<Record<SignUpField | "form", string>>;

export const INVITE_INVALID_MESSAGE =
  "This invite is invalid, expired, or already used. Ask an admin for a new link.";
export const RATE_LIMITED_MESSAGE =
  "Too many attempts. Please wait a minute and try again.";
export const BANNED_MESSAGE = "This account has been suspended.";

/**
 * Validate a `?next=` return-to candidate. Only same-origin relative paths
 * are allowed: it must start with a single "/" so absolute URLs
 * (https://evil.example), protocol-relative URLs (//evil.example) and
 * backslash tricks (/\\evil.example) are rejected.
 * Returns the path to redirect to, or null when unsafe/absent.
 */
export function sanitizeNextPath(next: unknown): string | null {
  if (typeof next !== "string" || next.length === 0) return null;
  if (!next.startsWith("/")) return null;
  if (next.startsWith("//") || next.startsWith("/\\")) return null;
  if (/[\u0000-\u001f\\]/.test(next)) return null;
  return next;
}

/** Human-readable message for an auth API failure, by form context. */
export function authErrorMessage(error: unknown, mode: AuthFormMode): string {
  const status = error instanceof ApiError ? error.status : 0;
  const raw = error instanceof ApiError ? error.message : "";

  if (status === 429) return RATE_LIMITED_MESSAGE;
  if (
    mode === "signup" &&
    /invite/i.test(raw) &&
    (status === 400 || status === 403 || status === 422)
  ) {
    return INVITE_INVALID_MESSAGE;
  }
  if (status === 403) {
    if (/csrf|cross-origin/i.test(raw)) {
      return "Session security check failed. Please refresh the page and try again.";
    }
    if (mode === "signup") return "Sign-ups are currently closed — a valid invite is required.";
    return BANNED_MESSAGE;
  }

  if (mode === "login") {
    if (status === 401) return "Invalid login or password.";
    return "Sign-in failed. Please try again.";
  }
  if (mode === "signup") {
    if (status === 409) return "An account with this email or username already exists.";
    if (status === 422) return "Please check the form — some fields are invalid.";
    return "Could not create the account. Please try again.";
  }
  if (mode === "forgot") {
    return "Could not send the reset request. Please try again.";
  }
  // mode === "reset"
  if (status === 400 || status === 404 || status === 410) {
    return "This reset link is invalid or has expired. Please request a new one.";
  }
  if (status === 403 && /token|reset/i.test(raw)) {
    return "This reset link is invalid or has expired. Please request a new one.";
  }
  return "Could not reset the password. Please try again.";
}

const KNOWN_FIELD_WORDS: Array<[RegExp, SignUpField]> = [
  [/invite/i, "invite"],
  [/\bemail\b/i, "email"],
  [/\buser\s*name\b|\busername\b/i, "username"],
  [/\bpassword\b/i, "password"],
];

function mapServerField(name: string): SignUpField | null {
  const n = name.toLowerCase();
  if (n === "invite" || n === "invite_token") return "invite";
  if (n === "email") return "email";
  if (n === "username" || n === "login") return "username";
  if (n === "password" || n === "new_password") return "password";
  if (n === "display_name") return "display_name";
  return null;
}

function keywordFieldErrors(message: string): AuthFieldErrors {
  const out: AuthFieldErrors = {};
  for (const [re, field] of KNOWN_FIELD_WORDS) {
    if (re.test(message)) out[field] = message;
  }
  return out;
}

/**
 * Best-effort extraction of per-field sign-up errors from an API failure.
 * Handles FastAPI 422 lists ({loc, msg}), {detail: {field: message}} objects,
 * and falls back to keyword matching inside plain detail strings.
 * Returns null when nothing field-specific could be identified.
 */
export function signUpFieldErrors(error: unknown): AuthFieldErrors | null {
  if (!(error instanceof ApiError)) return null;

  let parsed: unknown;
  try {
    parsed = JSON.parse(error.message);
  } catch {
    parsed = error.message;
  }

  const out: AuthFieldErrors = {};

  if (Array.isArray(parsed)) {
    for (const item of parsed) {
      if (!item || typeof item !== "object") continue;
      const loc = (item as { loc?: unknown }).loc;
      const msg = (item as { msg?: unknown }).msg;
      if (!Array.isArray(loc) || typeof msg !== "string") continue;
      for (let i = loc.length - 1; i >= 0; i--) {
        const field = mapServerField(String(loc[i]));
        if (field) {
          out[field] = msg;
          break;
        }
      }
    }
    return Object.keys(out).length > 0 ? out : null;
  }

  let detail: unknown = parsed;
  if (parsed && typeof parsed === "object" && "detail" in parsed) {
    detail = (parsed as { detail: unknown }).detail;
  }

  if (detail && typeof detail === "object" && !Array.isArray(detail)) {
    for (const [k, v] of Object.entries(detail)) {
      const field = mapServerField(k);
      if (field && typeof v === "string") out[field] = v;
    }
    return Object.keys(out).length > 0 ? out : null;
  }

  if (typeof detail === "string" && detail.length > 0) {
    // Only attach string details to fields for validation-shaped statuses —
    // a 401/403/409 detail is a form-level story, not a field story.
    if (error.status === 400 || error.status === 422) {
      const keywordOut = keywordFieldErrors(detail);
      if (Object.keys(keywordOut).length > 0) return keywordOut;
    }
  }

  return null;
}

/** Turn a backend `url_path` (e.g. "/login?invite=x") into an absolute URL. */
export function absoluteUrl(urlPath: string): string {
  if (typeof window === "undefined" || !window.location?.origin) return urlPath;
  return `${window.location.origin}${urlPath}`;
}
