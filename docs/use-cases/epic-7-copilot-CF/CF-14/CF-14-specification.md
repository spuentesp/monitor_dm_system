# CF-14: Share Session Artifacts with Players

**Actor:** Human GM (publish), Player with the link (read)
**Trigger:** Wrap-up / Handouts panel → Publish; player opens `/share/{token}`

**Purpose:** Close the recap/handout loop with players — CF-2 and CF-6
promise "export as Markdown, share with players", but the only affordance
before this was a client-side Copy button.

**Flow (GM):**

1. GM wraps up a session (CF-2) or generates a handout (CF-6).
2. GM clicks **Publish to players** (story-scoped share link is created on
   first publish; revocable at any time).
3. GM copies `/share/{token}` and sends it to the party (any channel).
4. GM can **Unpublish** an item or **Revoke** the link — both take effect
   on the very next request.

**Flow (Player):**

1. Player opens the link — no account, no login.
2. The page lists **published** recaps and handouts only (never the CF-8
   queue, never GM notes, never drafts).
3. If any handout is character-scoped, the player picks who they are; the
   server then shows a handout only when the scoped character matches, or
   when the viewer already witnessed **every** source fact it draws on
   (no new spoilers).
4. Any visible item can be downloaded as Markdown (`.md`).

**Out (v1):** player accounts/comments, per-player personalized views
(v1 = party-level), email delivery, PDF export (renderer deferred).

### Implementation

**Layer 1 (Data Layer):**
```python
# schemas/player_share.py + tools/mongodb_tools/player_share.py
mongodb_create_player_share(params)          # token = secrets.token_urlsafe(32)
mongodb_get_player_share_by_token(token)     # revoked/expired included
mongodb_get_player_share_for_story(story_id) # latest active only
mongodb_revoke_player_share(story_id, owner_id, universe_id)
mongodb_create_shared_artifact(params)       # published flag, Mongo only
mongodb_list_shared_artifacts(story_id, published_only=True)
mongodb_set_shared_artifact_published(artifact_id, universe_id, owner_id, published)
```

**Layer 2 (Agents):**
- `ShareAgent` (`monitor_agents/player_share.py`):
  - `resolve_share(token)` — unknown/revoked/expired all raise the same error
  - `publish / unpublish / revoke` — owner+universe predicated
  - `build_player_view(story_id, token, character_id=None)` — published-only,
    server-side spoiler resolution via `cast.filter_visible_facts`
    (the same witnessed-facts logic CF-6 specifies as
    `get_character_knowledge` — shared, never duplicated)
  - `export_markdown(artifact)`

**Layer 3 (UI):**
```
GET  /api/share/{token}                    # list + roster (?viewer_character=)
GET  /api/share/{token}/recap/{id}
GET  /api/share/{token}/handout/{id}
GET  /api/share/{token}/export/{id}.md     # text/markdown attachment
POST /api/gm/share/link|publish|unpublish|revoke   # authenticated, owner-checked
```
Frontend: public page `app/share/[token]/page.tsx`, publish toggles in
`WrapUpModal` and the Handouts panel.

**Rate limiting:** `SHARE_RATE_LIMIT` (default 120/min) per client IP +
token on every `/api/share/*` read; over-limit answers 429.

---
