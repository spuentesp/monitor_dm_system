---
description: "SillyTavern / RisuAI ecosystem interop — character card import/export, lorebook runtime semantics, card macros, and lorebook directives."
tags: [interop, character-card, lorebook, sillytavern, risuai, import]
layer: 1
---

# Ecosystem Interop (Cards & Lorebooks)

**Intent:** MONITOR speaks the open roleplay ecosystem's language. A user
arriving from Character.AI, SillyTavern, RisuAI, or Chub can drop a
character card (JSON or PNG) and have it parse *and behave* faithfully —
including its embedded lorebook, its macros, and its self-managing lorebook
directives. Cards enter the light-RP character store directly; canon
promotion is a separate, opt-in pipeline.

**Sources:**
- Card parse/serialize: `packages/ui/backend/src/monitor_ui/routers/character_cards.py`
- Import/export endpoints: `packages/ui/backend/src/monitor_ui/routers/entities.py` (`POST /characters/import-card`, `GET /characters/{id}/export-card`)
- Lorebook interop: `packages/data-layer/src/monitor_data/interop/sillytavern_lorebook.py`
- Lorebook schema + scan engine: `packages/data-layer/src/monitor_data/schemas/lorebook.py`, `packages/data-layer/src/monitor_data/tools/mongodb_tools/lorebook_tools.py`
- Lorebook endpoints: `packages/ui/backend/src/monitor_ui/routers/lorebook.py` (`POST /lorebook/import`, `GET /lorebook/export`)
- Card macros: `packages/data-layer/src/monitor_data/interop/card_macros.py`
- Output directives: `packages/agents/src/monitor_agents/lorebook_directives.py`

## Character card import

`POST /characters/import-card` accepts:

- **CCv2/CCv3 raw JSON** — v2/v3 nest fields under `data`; v1 flat cards are
  also tolerated.
- **PNG-embedded cards** — the `chara` / `ccv3` keywords in `tEXt`/`zTXt`
  chunks, base64-encoded JSON (the TavernAI/SillyTavern packaging).
- **CharX archives** (`.charx`, RisuAI) — the zip's `card.json` is parsed
  like any CCv3 card, and the icon asset (resolved from the `data.assets`
  declaration, with an `assets/icon/` fallback) is uploaded to MinIO and
  bound as the character's avatar. Non-icon assets (emotions, backgrounds)
  are not imported yet.

Field mapping: `description`/`char_persona` → description, `personality` →
personality, `first_mes`/`char_greeting` → first message, and
`system_prompt` + `scenario` + `creator_notes` + `mes_example` → GM notes.
An embedded `character_book` is parsed into lorebook entries plus a
book-level scan config (same importer as standalone lorebooks).

`GET /characters/{id}/export-card` serializes back to a `chara_card_v2`
object, embedding the character's lorebook entries as `character_book`.
Unmapped ST fields survive the round trip via `st_extensions`.

## Lorebook runtime semantics

The scan engine (`mongodb_scan_lorebook`) runs at prompt assembly in both
the ConversationLoop and ContextAssembly, and honors the SillyTavern
feature set imported cards rely on:

- **Keyword matching** — plain or whole-word regex, per-entry or global
  case sensitivity, comma-separated keyword lists.
- **Selective logic** — secondary keywords with AND ANY / NOT ALL /
  NOT ANY / AND ALL.
- **Constant entries**, **probability rolls**, **vectorized flag**.
- **Timing** — `delay`, `sticky`, `cooldown` windows tracked per turn index.
- **Inclusion groups** — group competition keeps the highest-priority
  member; `group_override` bypasses.
- **Recursion** — matched content is re-scanned, with
  `prevent_recursion` / `exclude_recursion` guards and a hard cap.
- **Scan depth & token budget** — book-level `LorebookScanConfig` controls
  how many recent turns are scanned and the injected-token ceiling
  (rough chars/4 estimate).
- **Insertion positions** — results are grouped `before` / `after` /
  `@depth` and injected at the matching point in the assembled prompt.

## Card macros

`{{char}}` and `{{user}}` (case-insensitive, optional inner whitespace,
plus the legacy `<CHAR>`/`<USER>` aliases) are resolved **at render time**,
never at import time — the stored card stays raw so exports remain
faithful. Substitution happens:

- when a light-RP character is provisioned into an entity + NPC profile
  (description, personality, GM notes), and
- when the opening `first_message` is rendered.

`{{user}}` resolves to the bound persona's name:
`POST /characters/{id}/conversations` accepts an optional
`persona_character_id` pointing at a character with `is_ooc_persona=true`;
without one it falls back to `"User"` (the SillyTavern default). A bound
persona is also injected into the NPC voice prompt as
`"name — description"` (`player_persona` in the ConversationLoop state),
persisted on the conversation document so resumed sessions keep it.

## Lorebook directives

Two directive mechanisms are supported:

- **Output directives** (`@@activate <name>` / `@@deactivate <name>`):
  lines the model emits in its reply are stripped from the player-visible
  prose and toggle the matching lorebook entry's `is_active` flag (matched
  by `comment`, case-insensitive, across the conversation's lorebook
  characters). Unmatched names are skipped silently; failures never break
  a turn.
- **Content decorators** (import time): leading `@@position` / `@@depth` /
  `@@probability` / `@@order` lines at the top of an entry's content
  override the structured fields and are stripped from stored content, per
  ST semantics. Unknown decorators (`@@role`, `@@is_greeting`, ...) end the
  block and are preserved verbatim.

## OpenAI-compatible endpoint

`POST /api/v1/chat/completions` accepts an OpenAI-shaped `ChatCompletionRequest`
(`model`, `messages`, `temperature`, `max_tokens`, `top_p`, `stream`) and
returns an OpenAI-shaped `ChatCompletion` (`id`, `object`, `created`,
`model`, `choices[].message`, `usage`). RisuAI / SillyTavern / LiteLLM can
point at MONITOR as a backend by configuring the URL to
`http://<monitor-host>:8000/api/v1`.

**Routing modes (chosen by the request body):**

- **Plain OpenAI** (no session fields): one LM call via `LLMRegistry`.
  Supports streaming (SSE, OpenAI `chat.completion.chunk` shape) and
  non-streaming. `stream_text` on `LLMClient` bridges
  `chat.completions.create(stream=True)` for OpenAI-compatible providers
  and `messages.stream(...)` for Anthropic / MiniMax.
- **Session mode** (`monitor_session_id` or `character_id`): the request
  is routed through the light-RP conversation loop, so the response
  benefits from persona binding, lorebook scanning, and NPC memory.
  `stream=true` is rejected (HTTP 400) — the conversation loop is
  non-streaming today; reply is one assistant message.

**Card binding:** session mode threads a `persona_character_id` through
`start_conversation` for the same `{{user}}` / voice-prompt depth that the
native light-RP surface has. The character card itself rides on
`character_id` (server looks it up and provisions the incarnation).

**Auth:** open in v2 (same dev binding as the rest of the UI backend).
Front with reverse-proxy auth or add a bearer-token middleware before
exposing publicly.

The `model` field is accepted for client compatibility; plain-mode calls
are routed through `LLMRegistry` at the `STANDARD` role (the configured
default chat model). The response echoes the request value.

## Canon promotion (v1)

`POST /api/entities/characters/{id}/promote` is the lever that turns a
light-RP session into canonical proposals. The route finds the active
conversation (or one explicitly by id), runs ``SessionListenerModule`` on
its turns, and writes each event / lore item / active thread to the
``proposed_changes`` collection with the conversation id anchored in
``content`` and the proposer tagged ``character_promotion:<character_id>``.

The response is a ``PromotionPreview`` with per-kind counts and the list
of proposal ids:

```json
{
  "character_id": "char-1",
  "conversation_id": "conv-1",
  "events_proposed": 2,
  "lore_proposed": 1,
  "threads_proposed": 0,
  "proposal_ids": ["..."],
  "skipped": []
}
```

Status pending; the user commits them via the existing CanonKeeper flow
(``POST /api/canon-review/...``). Entity resolution via Qdrant and the
user-facing diff view are the next tightening pass.

**v1 deliberately skips:**

- Qdrant entity dedup (no "is imported Elara the same as the ranger of
  the eastern woods?" gate). The promotion writes everything; CanonKeeper
  + a future review step resolve duplicates.
- The "is this a conflict?" verdict. CanonKeeper evaluates each proposal
  individually when committed.
- A 1:1 mirror of the funnel doc's full promotion UX. The
  ``PromotionPreview`` is the small surface; a real diff UI lives behind
  it.

## Known gaps

- **CharX non-icon assets** — emotion/background images are not imported
  (only the icon becomes the avatar).
- **Group chat** — no multi-character speaker selection.
- **OpenAI session-mode streaming** — `stream=true` is rejected in session
  mode because the conversation loop has no streaming surface. A future
  pass would extend `NPCVoice` to stream the LLM call.
- **Canon promotion dedup + conflict UX** — the v1 promotion writes
  proposals directly; Qdrant semantic dedup and the "3 conflicts, pick
  per item" diff view are the next layer.
- **Inbound OpenAI-compatible endpoint** — RisuAI/SillyTavern cannot yet
  point at MONITOR as a `/v1/chat/completions` backend.
- **Canon promotion of imported cards** — imports land in the light-RP
  store; the proposal/entity-resolution pipeline is separate future work.
