# G07 — Player-facing recap & handout sharing (proposed CF-14)

> **Status:** proposed 2026-11-11. Gap: CF-2/CF-6 promise "export as
> Markdown, share with players", but the only affordance today is a
> client-side Copy button (`RecapModal.tsx:13-29`). No export endpoint, no
> read-only player view — the players, who most need the recap, get nothing
> from the system.

## Goal

Give players a read-only view of what their party is allowed to see:
session recaps (CF-2), campaign arc recap (CF-12), and GM-approved handouts
(CF-6) — via a share link scoped to a story, with spoiler controls
enforced server-side, plus Markdown/PDF export for the GM.

## Use case

Propose **CF-14 "Share Session Artifacts with Players"**; amends CF-2 step 5
and CF-6 step 4.

## Scope

**In:** shareable link per story (`/share/{token}` — unauthenticated but
unguessable token, owner-revocable, tenancy-scoped); player view lists
published recaps + handouts only (never the CF-8 queue, never GM notes,
never draft proposals); GM "publish" toggle per recap/handout; handout
spoiler levels (party / specific character) resolved **server-side** from
witnessed facts; Markdown export (`.md` download) for GM; PDF export deferred.
**Out (v1):** player accounts/comments on shared artifacts, per-player
personalized views (v1 = party-level), email delivery.

## Design

- **Layer 1:** `schemas/player_share.py` (share token doc: story_id,
  owner_id, revoked flag, published item ids) + `mongodb_tools/player_share.py`;
  recap/handout docs gain a `published: bool` field (Mongo only; canon
  untouched).
- **Layer 2:** `ShareAgent` (new, `monitor_agents/player_share.py`) —
  `publish(item)`, `build_player_view(story_id, token)` which filters by
  spoiler level using the same witnessed-facts logic as CF-6
  (`get_character_knowledge`), and `export_markdown(item)`.
- **Layer 3:** public router `routers/player_view.py`
  (`GET /share/{token}`, `GET /share/{token}/recap/{id}`,
  `GET /share/{token}/handout/{id}`, `GET /share/{token}/export/{id}.md`)
  with rate limiting and **no** `get_current_user` requirement (token is the
  credential); GM-side `POST /gm/share/publish|revoke` in `gm_tools.py`;
  frontend: public Next.js page `app/share/[token]/page.tsx` + publish
  toggles in WrapUpModal/handouts panel.

## Phases

1. Token schema + tools + tests (revocation, scoping, expiry).
2. ShareAgent + tests (spoiler filtering must reuse CF-6's witnessed-facts
   query — do not duplicate the logic; fake clients).
3. Public routes + abuse tests (revoked token → 404/410, cross-owner → 404,
   rate limit); authz regression style of `test_cf_authz_regressions.py`.
4. GM publish UI + public player page; vitest for both.
5. Markdown export; live verification entry.

## Acceptance

- GM publishes a recap; a player opening the share link sees only
  published items, with character-scoped handouts filtered server-side.
- Revoking the token or unpublishing an item immediately blocks access.
- No draft/GM-only data is reachable through any `/share/*` route (tested).
- Commits reference CF-14; tests green; layer check clean.

## Open decisions

- Token model: single per-story token (v1) vs. per-artifact links.
- PDF export: needs a renderer (defer; Markdown v1).
- Player identity on shared links: anonymous-with-token v1; accounts later.

## Live verification checklist (Phase 5)

Run once against the Docker stack (`./dev.sh`) — hermetic tests cover the
logic; this pass proves the wiring end-to-end. Append results with date.

1. [ ] Wrap-up a gm_assistant recording → **Publish recap to players** →
       copy the `/share/{token}` link from the modal.
2. [ ] Open the link in a private window (no login): the published recap
       renders; a *draft* or unpublished item id returns 404.
3. [ ] Publish a handout from the Handouts panel (pick a story first);
       confirm it appears on the share page with a working **Download .md**.
4. [ ] **Unpublish** the handout → refresh the share page → it is gone;
       direct `/share/{token}/handout/{id}` now 404s.
5. [ ] Publish a character-scoped handout via
       `POST /api/gm/share/publish` (`spoiler_level: "character"`,
       `scope_character_id`, `source_fact_ids`) → on the share page the
       item is hidden for "The whole party" and for the wrong character,
       visible when the scoped character is selected; a party member who
       witnessed all source facts also sees it.
6. [ ] **Revoke** the link → the share page shows "no longer available"
       (404) for every route, including `export/*.md`.
7. [ ] Hammer one token > `SHARE_RATE_LIMIT` within a minute → 429.
8. [ ] `uv run ruff check packages`, `python scripts/check_layer_dependencies.py`,
       and the CF-14 test files all green.

