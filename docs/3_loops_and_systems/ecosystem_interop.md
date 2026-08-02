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
without one it falls back to `"User"` (the SillyTavern default). Persona
resolution is name-only for now — the persona's description is not yet
injected into the voice prompt.

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

## Known gaps

- **CharX non-icon assets** — emotion/background images are not imported
  (only the icon becomes the avatar).
- **Persona depth** — persona binding resolves `{{user}}`'s name only; the
  persona's description/personality is not injected into prompts yet.
- **Group chat** — no multi-character speaker selection.
- **Inbound OpenAI-compatible endpoint** — RisuAI/SillyTavern cannot yet
  point at MONITOR as a `/v1/chat/completions` backend.
- **Canon promotion of imported cards** — imports land in the light-RP
  store; the proposal/entity-resolution pipeline is separate future work.
