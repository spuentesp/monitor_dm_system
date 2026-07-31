# MONITOR UI Redesign — Two-Tier Hub Design Spec

**Date:** 2026-07-31
**Status:** Approved (design review complete, awaiting implementation plan)
**Scope:** Landing/lobby redesign, Light RP screen, Workbench consolidation, Configuration section, LLM-integrated image generation

## Problem Statement

The current MONITOR web UI has user-facing friction:

- Active world and system mode are buried as tiny native `<select>` dropdowns in the sidebar footer (`WorldPicker`, `ModeSwitcher`).
- No standalone "my games / sessions" or "worlds" page — sessions live inside `/play`, universes inside `/forge/worlds`.
- The play setup panel exposes the full multiverse → universe → system → character hierarchy as a chain of dropdowns.
- The `/universes` link in `SetupPanel.tsx` is a dead route (404).
- No discoverable place to see or manage the many configurable moving parts (LLM roles, prompts, retrieval tunables).
- No image-generation integration.

## Approved Direction

Two-tier hub:

- **Lobby** (player tier) — landing. Two sub-screens: **Campaigns** and **Light RP**.
- **Workbench** (builder tier) — World Forge + GM Assistant only.
- **Configuration** — its own top-level section; agents, prompts, tunables, infrastructure.

Image generation is deliberately simple: configured alongside the other LLMs in the existing LLM registry, and used directly from character cards or chat logs.

## 1. Information Architecture

```
MONITOR
├─ LOBBY (player tier — landing, route: /)
│   ├─ Campaigns
│   │    ├─ Continue playing (recent sessions, one-click resume)
│   │    ├─ Playable universes (card grid with playable-state + latest story)
│   │    └─ New campaign (guided step wizard, replaces dropdown chain)
│   └─ Light RP (route: /light-rp — separate screen)
│        ├─ Character card grid (portrait, name, 1-line summary, Chat button)
│        ├─ Import SillyTavern card (JSON/PNG)
│        └─ Recent light chats (resume)
│
├─ WORKBENCH (builder tier — route: /workbench, keeps existing /forge, /gm content)
│   ├─ World Forge (universes, ingestion, packs, canon review, lorebooks)
│   └─ GM Assistant (dice, rules/books, prep, threads, handouts, ask-the-world chat)
│
└─ CONFIGURATION (route: /config)
     ├─ Agents & LLMs (LLM registry, per-role assignments incl. image-gen role)
     ├─ Prompts (prompt collections, DSPy modules, test playground)
     ├─ System tunables (retrieval, token budgets, lorebook scan defaults)
     └─ Infrastructure health (DB status)
```

**Navigation changes:**

- Sidebar groups become three labeled tiers with large icons: Lobby, Workbench, Configuration.
- Remove `WorldPicker` and `ModeSwitcher` footer dropdowns. World selection happens on universe cards; mode is implicit in the screen you are on.
- Fix the dead `/universes` link in `SetupPanel` (redirect to Workbench → World Forge worlds).

## 2. Lobby — Campaigns Tab

**Components:**

- `ContinuePlayingRail` — last N sessions: story title, turn count, relative timestamp, resume button.
- `UniverseCardGrid` — each card: universe name, story count, latest story title, playable-state badge (`ready` / `needs review` / `ingesting`), Play and Stories buttons.
- `NewCampaignWizard` — step wizard: (1) pick universe, (2) pick story or new, (3) pick/create character, (4) tone & begin. Replaces the multiverse/universe/system/PC dropdown chain in `SetupPanel`.

**Data:** existing endpoints — `chatApi.listSessions`, `universesApi.listUniverses`, `storiesApi.listStories`. Add one aggregation endpoint only if profiling shows N+1: `GET /api/lobby/overview` returning sessions + universes + latest stories in one payload.

## 3. Lobby — Light RP Screen

**Components:**

- `CharacterCardGrid` — card: portrait (or generated placeholder), name, one-line summary (first line of description), Chat button; overflow menu: Generate portrait, Edit, Export card, Delete.
- `ImportCardButton` — accepts SillyTavern `chara_card_v2` JSON or PNG (existing `routers/character_cards.py` interop, now including embedded `character_book` lorebooks).
- `RecentLightChatsRail` — recent `CharacterConversation` sessions with message count and resume.

**Data:** `entitiesApi.listStandaloneCharacters`, `entitiesApi.importCharacterCard`, `character_conversation.py` backend (existing conversatory).

**Future use cases (recorded, not implemented this round):**

- Convert a light-RP chat log into world data (entities/lore entries) for a universe or story.
- Per-character memory inspector on the card.

## 4. Workbench

- **World Forge** — existing advanced screens (`/forge/*`: worlds tree/graph, ingestion studio, packs, canon review, lorebook editor) move under `/workbench/forge/*` (redirects from old paths). Functionally unchanged; density is intentional — builders need it.
- **GM Assistant** — existing panels (dice, rules reference/books, session prep, unresolved threads, handouts) plus a new "Ask the world" chat panel that queries canon. Panels are modifiable: show/hide/reorder per user (persist layout in localStorage; no backend change).

## 5. Configuration

Route `/config`, four pages:

- **Agents & LLMs** — first-class page for the existing LLM registry (`llm_registry.py`, PostgreSQL-persisted, per-role model assignments). Provider list extended with **image providers** (MiniMax, nano-banana/Google, OpenAI images). A new `image_generation` role is assignable per provider, exactly like chat roles. This is the single place image-gen is configured.
- **Prompts** — prompt collections list + DSPy module inventory + small test playground (input → assembled prompt preview).
- **System tunables** — retrieval settings, token budgets, lorebook scan defaults (scan depth, token budget, recursion). Read-mostly; edits behind "advanced" toggles so the many variables are visible without overwhelming.
- **Infrastructure health** — existing DB health checks surfaced.

## 6. Image Generation

**Principle:** no standalone image tool. Generate where content lives.

**Configuration:** through the LLM registry (see §5) — provider + API key + model assigned to the `image_generation` role. Keys live in `.env`/provider secrets store, never in MongoDB.

**Backend:**

- New data-layer provider adapter: `monitor_data/llm/image_providers.py` — one interface `generate_image(prompt: str, **opts) -> bytes`, implementations for MiniMax and nano-banana (Google). Plugs into the existing registry/semaphore patterns.
- New UI-backend router `packages/ui/backend/src/monitor_ui/routers/image_gen.py`:
  - `POST /characters/{id}/generate-portrait` — builds prompt from card description + personality + gm_notes, calls the configured image provider, stores result in MinIO, sets the character's `avatar_url`, returns the new avatar URL.
  - `POST /conversations/{id}/generate-image` — builds prompt from last N messages + character info, returns the image without mutating the card.
- Prompt builder is a pure function, unit-testable: `build_portrait_prompt(character) -> str`, `build_scene_prompt(messages, character) -> str`.

**Frontend:**

- Character card: "✨ Generate portrait" button → calls portrait endpoint → swaps in image; "↻ Regenerate" and "Use as avatar" after success.
- Light-RP chat: per-message overflow action "🖼 Generate scene image" → calls conversation endpoint → displays inline.

**Errors:** missing provider config → actionable message linking to `/config`; provider failure/rate-limit → retryable error, never blocks chat.

## 7. Data Flow & Layer Rules

- No new databases. New MongoDB usage: none for image config (lives in LLM registry/PostgreSQL); generated images in MinIO (existing storage client).
- UI backend imports data-layer only; no CLI changes; CanonKeeper authority untouched (no graph writes from this work).
- `check_layer_dependencies.py` must pass.

## 8. Testing

- **Unit (data-layer):** image provider adapters (mocked HTTP), prompt builders.
- **API (tests/api):** new `image_gen` router endpoints; lobby overview endpoint if added.
- **Frontend:** Vitest + Testing Library component tests for `UniverseCardGrid`, `CharacterCardGrid`, `NewCampaignWizard`, navigation tiers; `lorebookApi`-style API mocks.
- **E2E:** extend `tests/e2e` with a lobby smoke path (list universes → start light-RP chat → import card). Image provider calls mocked.
- Existing suites must stay green (`packages/*`, `tests/api`).

## 9. Out of Scope (This Round)

- Light-RP → world-data conversion pipeline.
- Per-character memory inspector.
- Real LLM token streaming, swipes, message editing (known gaps, separate roadmap).
- Multiplayer/group chat.

## 10. Current-State Friction Being Resolved

| Friction (found in review) | Resolution |
|---|---|
| `WorldPicker`/`ModeSwitcher` tiny footer dropdowns | Removed; world chosen on universe cards, mode implicit per screen |
| No sessions/worlds page | Lobby Campaigns tab + Workbench |
| `/universes` 404 link | Redirected to Workbench worlds |
| Setup dropdown chain | New-campaign step wizard |
| Configurables invisible | `/config` section |
| No image generation | LLM-registry role + card/chat entry points |
