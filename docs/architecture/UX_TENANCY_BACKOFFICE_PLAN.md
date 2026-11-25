# UX, Tenancy Verification, Accounts & Backoffice — Plan

> **Status:** implemented 2026-11-20 on branch `ux/integration` (not yet merged to master). Hermetic suites green; the live two-user pass (UX-0/UX-1 step 1) and SMTP delivery are NOT yet exercised against a real stack. See "Implementation status" at the end.
> **Audience for this release:** a handful of invited users (not open signup).
> **Decisions (2026-11-19):**
> - Providers: **admin-only.** Keys stay behind admin in one shared pool; no per-user keys (BYOK dropped 2026-11-20).
> - Password reset: **both** — by email when SMTP is configured, and admin-issued reset link always.
> - Admin: **basics only** (users, invites, resets, usage caps, providers). No audit UI, pagination or drill-downs yet.
> - Signup: **invite-only** by default.
>
> Builds on [MULTI_TENANCY_PLAN.md](MULTI_TENANCY_PLAN.md) (what is enforced today).
> Reference this plan's phase IDs (`UX-1` …) in commits alongside the relevant use case IDs.

## Current-state findings (from code reading, not yet verified live)

- Tenancy enforcement is strong at HTTP and the most-used write tools; gaps are listed in MULTI_TENANCY_PLAN §4.
- Backend already has: password change, session list/revoke, API tokens, Google OAuth, usage caps API.
  **No frontend** for password change, sessions, tokens, or usage caps. `app/settings/` has no page.
- No password reset, no email verification, no invite mechanism. Signup is open.
- `/api/llm/*` is admin-only; providers are one shared pool. Keys are Fernet-encrypted only if
  `MONITOR_PROVIDER_KEY_ENCRYPTION_KEY` is set.
- `/admin` = users table only. Operator tools live inside the 2,456-line `config/page.tsx`.
- `gm/page.tsx` (1,936 lines) and `PlayConsole.tsx` (1,075 lines) are monoliths.
- `AuthGate` renders nothing while loading; login always redirects to `/` (no return-to).
- Unverified: whether non-admins see the Admin/Configuration sidebar links.

---

## Phase UX-0 — Baseline (≈1–2 days)

1. Run the stack with `MONITOR_AUTH_DISABLED=false`; create an admin plus users A and B.
2. Run `test_cross_tenant.py`, `test_route_auth_coverage.py`, `tests/e2e/test_tenancy_defense_in_depth.py` on master; record results.
3. Walk each flow (login → lobby → Auto GM play → GM Assistant → forge → admin) as admin and as a plain user; list defects in an issues table appended to this doc.
4. Check sidebar/route visibility for non-admins.

**Exit:** green baseline + defect list.

## Phase UX-1 — Tenancy verification and closure (≈1 week, do first)

1. **Live adversarial pass** with A/B through UI and API: ID substitution, direct URLs, WebSocket chat (4401/4404 paths), share links, `/v1/chat/completions`.
2. **Share-link review** (`/share/[token]`): token entropy, expiry, revocation, exact fields exposed to players.
3. **Close write-tool gaps** with `assert_*_write` + unit tests (pattern: `test_tenancy_tool_guards.py`). Order: lorebook, knowledge packs, play sessions, combat, game systems.
4. **Fix blanket 502 wrappers** (image-gen, gm_tools LLM handlers) so `QuotaExceededError` → 429 and `OwnerViolationError` → 404.
5. **Ingest jobs:** make the strict creator match the rule everywhere, or document the exception.
6. Keep `SWEEP_EXEMPT` and `PUBLIC_ROUTES` allowlists reviewed; confirm both tests run on every PR.
7. **New for invites/reset:** every new route in UX-2/UX-3 ships with cross-tenant sweep coverage (the sweep picks up resource-id routes automatically; add explicit cases for invite resources).

**Exit:** adversarial pass finds no cross-tenant read/write; new guard tests green; layer check passes.

## Phase UX-2 — Accounts: invites, reset, account page (≈1.5 weeks)

### Invite-only signup
- New table `invites` (token hash, email optional, created_by, expires_at, used_by, used_at, revoked_at).
- `MONITOR_SIGNUP_MODE` = `invite` (default) | `open` | `closed`. `/auth/config` reports it; login page hides "Create account" unless open, and shows "Have an invite?" instead.
- `POST /auth/signup` requires a valid invite token in `invite` mode; token is single-use and consumed atomically with account creation.
- Admin creates invites (UX-3); invite link `…/login?invite=<token>` opens sign-up prefilled.
- Google OAuth first-login follows the same rule (no invite → no new account).

### Password reset (email **and** admin-issued)
- One mechanism: `password_resets` table (token hash, user_id, expires ≤1h, used_at).
- **Email path:** `MONITOR_SMTP_*` env vars; "Forgot password?" on login → `POST /auth/password/forgot` always returns 202 with the same body (no user enumeration), rate-limited per IP and per account. If SMTP is unset the endpoint still returns 202 and the UI says "ask your admin for a reset link".
- **Admin path:** admin clicks "Reset password" on a user → one-time link shown once for copy (works without SMTP).
- `POST /auth/password/reset` consumes the token, sets the password, **revokes all sessions** for that user. Tokens single-use, stored hashed.
- Optionally mark `email_verified` when a reset or invite email round-trip succeeds.

### Account page (`/settings/account`)
- Profile; change password; active sessions (revoke one / all others); API tokens (create, copy once, revoke). Backend routes exist; build the UI.

### Login/session polish
- `?next=` return-to; preserve destination on 401; "session expired" toast instead of silent redirect; skeleton instead of blank `AuthGate`; show-password toggle; per-field errors; distinct banned / rate-limited messages.
- User menu in sidebar footer (name, account, sign out); hide Admin/Configuration for non-admins.

**Exit:** invited user can sign up, sign in, change password, reset via both paths, manage sessions/tokens; uninvited signup is refused (tests for single-use, expiry, enumeration-safety, session revocation).

## Phase UX-3 — Admin basics (≈1 week)

Keep it small: a handful of users.

- Split `/admin` into tabs: **Users**, **Invites**, **Usage**, **Providers (shared)**.
- **Users:** existing ban/unban/role, plus *Reset password* (issues link), *Revoke sessions*. Confirmation dialog on ban and role change; ban reason in the dialog.
- **Invites:** create (optional email, expiry), copy link, list, revoke.
- **Usage:** per-user daily tokens/calls today vs cap (uses existing `/api/admin/usage*`); edit caps and `exempt`; "over cap" badge.
- **Providers:** move the LLM-provider management out of `config/page.tsx` into admin (the other config tabs stay put for now). Keys write-only, last-4 shown.
- **Ownership backfill** button with dry-run preview.
- Minimal accountability without a UI: structlog `admin_action` events (actor, target, action) for ban/role/reset/limits/invite.

**Deferred (not needed at this size):** pagination/filters, user drill-down, audit table + viewer.

**Exit:** an operator can onboard, reset, cap and ban a user entirely from the UI.

## Phase UX-4 — Provider keys stay admin-only (≈2–3 days)

No BYOK. One shared pool, managed by admins (UX-3 Providers tab). This phase only hardens and explains it:

1. **Encryption mandatory outside local mode:** refuse to start (or refuse to save a key) when `MONITOR_PROVIDER_KEY_ENCRYPTION_KEY` is unset and `MONITOR_AUTH_DISABLED` is false; keep the warning in local mode. Run `scripts/migrate_encrypt_provider_keys.py` on existing rows.
2. **Non-admin surface:** `/api/llm/*` stays 403 for non-admins (already tested); the UI never links to it. Confirm responses never echo a key (last-4 only) and errors/logs never include one.
3. **User-facing messaging:** when the shared pool is unconfigured or a user is over cap, show "ask your admin" (429 → "daily limit reached, resets 00:00 UTC; ask your admin to raise it"), not a raw error.
4. **Tests:** non-admin cannot list/read/use-by-id/modify providers; key never present in any response body.

**Exit:** keys encrypted at rest in non-local mode; non-admins cannot reach them; limit/unconfigured states are readable.

## Phase UX-5 — GM Assistant UX (≈1.5 weeks; parallelizable)

1. Prep → Run → Wrap-up stepper atop `/gm`; recorder is the default "Run" view.
2. Split `gm/page.tsx` into `components/gm/` panels; page becomes a layout shell.
3. First-run: no-universe guided picker; short first-use tour (dice, rules lookup, recorder).
4. Table ergonomics: keyboard shortcuts (roll, add note, next entry), larger touch targets, banner when the LLM/provider is down while dice and notes keep working.
5. Loading/cancel on AI panels (insights, contradictions, ask-the-world).
6. 429 → "daily limit reached, resets 00:00 UTC; ask your admin" (see UX-4).

## Phase UX-6 — Auto GM UX (≈1.5 weeks; parallelizable)

1. Live review of `PlayConsole`: time-to-first-token, streaming smoothness, retry, scroll, WebSocket drop/recovery.
2. One onboarding path merging `NewCampaignWizard` and `SetupPanel`, with a one-click quick start.
3. Turn controls: regenerate, edit-last-turn, undo; visible roll result with reasoning.
4. Inline canon transparency: what the GM proposed, badge linking to `CanonReviewPanel`.
5. Split `PlayConsole.tsx` into session/WebSocket hooks and presentational components.
6. Phone-width pass (composer, side panels, recap modal).

## Phase UX-7 — Cross-cutting (parallel)

- Standardize on `DialogShell`, shared empty/error states; breadcrumbs.
- Accessibility: focus order, icon-button labels, contrast, `aria-live` for streamed chat.
- Tests: vitest per new component; one e2e for login → play → admin; one e2e "user B cannot see user A's world through the UI"; one e2e for invite → signup → reset.

---

## Ordering and effort

UX-0 → UX-1 first (tenancy correctness precedes inviting anyone). UX-2 → UX-3 → UX-4 are sequential (invites and reset are needed before onboarding users; UX-4 is a short hardening pass on the admin Providers tab). UX-5, UX-6, UX-7 can run in parallel agent worktrees after UX-2.
Total ≈ 7–8 weeks for one person; ≈ 4–5 with parallel agents on UX-5/6/7.

## Rules for every phase

- Layers: UI backend → agents → data-layer only; no CLI/data-layer shortcuts.
- Tests with every change; never touch `tests/verification/**` or `tests/property/**`.
- Run `scripts/check_layer_dependencies.py`, ruff, strict mypy, and the cross-tenant suite before merging.
- `structlog` only; no `print()`.

## Open items

- SMTP provider/credentials (needed only for the email reset path).

## Implementation status (2026-11-20)

| Phase | State |
|---|---|
| UX-0 baseline | Hermetic only (full suite 10,553 passed, mypy/ruff/layer check clean). **Live walkthrough not done** — needs an isolated stack, not the dev databases. |
| UX-1 tenancy | Write-tool guards (lorebook, packs, play sessions, combat, game systems), typed-error re-raise, strict ingest creator match, share-link fix, WS close-code tests done. **Live adversarial pass still to do.** Remaining HTTP-only write families listed in MULTI_TENANCY_PLAN §4. |
| UX-2 accounts | Invites, signup modes, password reset (email + admin link), single-session revoke, login/forgot/reset pages, account page, AuthGate. Email delivery untested against a real SMTP server. |
| UX-3 admin | Users/Invites/Usage/Providers tabs, confirmations, reset link, revoke sessions. |
| UX-4 provider keys | Admin-only; encrypted saves enforced outside local mode. |
| UX-5 GM Assistant | Page split, stepper, first-run, shortcuts, cancel, quota message. |
| UX-6 Auto GM | PlayConsole split, reconnect/cancel, rewind-based undo/edit/regenerate, canon badge, quick start, mobile. Known limit: ConversationLoop memory and the Mongo SceneLoop checkpoint are not rolled back by rewind. |
| UX-7 cross-cutting | Sidebar user menu, admin links hidden for non-admins, aria-live/labels in play. Playwright e2e not written. |
