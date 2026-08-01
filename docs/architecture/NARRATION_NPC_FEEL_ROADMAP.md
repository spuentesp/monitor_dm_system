# Narration Quality & NPC Feel — Idea Backlog

> **Status:** brainstorm, not yet committed. Compiled from a platform-comparison
> discussion (AI Dungeon, NovelAI, SillyTavern, Character.AI) against MONITOR's
> current GM loop. Goal stated by the user: improve narration **quality** and
> **NPC feel** — not a general feature wishlist.

## Verified current-state finding (informs #1 below)

Investigated the user's assumption that "CanonKeeper should have NPC
relationship memory" before prioritizing anything on top of it:

- **CanonKeeper's relationship handling is static canon graph edges**
  (`entity_relationship` proposals → Neo4j `RELATIONSHIP` edges with a
  `category`, e.g. "Alice ALLY_OF Bob") — `canonkeeper/agent.py:1814
  _commit_relationship`, `:1916 _commit_entity_relationship`. This is
  world-fact bookkeeping, not a dynamic per-player relationship read on an NPC.
- **The dynamic, quantified relationship system already exists — fully
  built — in `npc_voice/agent.py`**: `_relationship_snapshot`/
  `_build_relationship_snapshot` track `trust`/`affinity`/`fear`/`leverage`/
  `familiarity`/`interest`/`stance` per `(npc, player, universe)`, persisted via
  `mongodb_update_npc_profile` on `relationship_states_by_universe` (`npc_voice/agent.py:475-886`).
  The `mongodb_get_npc_profile`/`mongodb_update_npc_profile` MCP tools are
  registered and working (`mongodb_tools/npc_profiles.py`).
- **This system is wired ONLY into light-RP** (`conversation_loop.py` →
  `NPCVoice`). The full GM Play loop's context builder
  (`context_assembly/agent.py::assemble`) and the Narrator
  (`narrator/agent.py`) have **zero references** to `npc_profile` or
  `relationship_states_by_universe` — verified by grep, not inference. NPCs
  encountered in normal Play have no memory of how the player treated them,
  even though the mechanism to give them that memory is sitting unused one
  layer away.

This changes the shape of idea #1 from "build NPC relationship memory" to
"wire an existing, working system into a second call site" — much smaller
and lower-risk than it sounded going in.

## Ideas

| # | Idea | What it fixes | Impact (quality/NPC-feel) | Effort | Notes |
|---|------|----------------|---------------------------|--------|-------|
| 1 | **Wire NPC relationship memory into full Play** | NPCs in the main GM loop don't remember how the player treated them | **High** — direct "this feels alive" driver | **Medium** | Infra fully built in `NPCVoice`; work is fetching `npc_profile` per scene NPC in `context_assembly.assemble()` and threading the snapshot into the actor block `narrator.py` already builds (same pattern as the hallucination-guard actor block) |
| 2 | **Per-NPC voice anchors** | All NPC dialogue reads as one GM voice | **High** — distinctiveness is a top "doesn't feel real" complaint | **Low–Medium** | A few example lines per NPC (reuse `npc_profile` storage), same idea as GM-level voice anchoring but scoped per-character |
| 3 | **Anti-repetition / banned-phrase list** | Model tics ("a shiver runs down your spine...") recur turn after turn | **Medium–High** — cheap, well-known fix | **Low** | Player-curated list injected as a negative constraint; nearly universal on serious RP frontends |
| 4 | **GM-level voice-anchor seeding** | Generic/flat prose voice overall | **Medium** | **Low** | Few example lines of actual GM prose (not adjectives) in the profile/system prompt |
| 5 | **Editable rolling memory summary** | Silent context-compaction drops things the player cared about | **Medium** — turns invisible drift into something fixable | **Medium** | Surface the current compression summary (`ContextAssembly.check_and_compress_if_needed`) as player-readable/editable |
| 6 | **Surface active lore/facts** | Weird narration reads as random when retrieval is invisible | **Medium** | **Low–Medium** | Show which lorebook/established-fact entries fired this turn (AI Dungeon World Info pattern) |
| 7 | **Global tone/genre preset** | One-size prose register regardless of desired vibe | **Medium** | **Low** | Noir/pulp/cozy/grimdark dial, decoupled from the ruleset |
| 8 | **Pacing/tempo dial** | GM loop rushes or drags relative to what the player wants | **Medium** | **Low–Medium** | Explicit "slow down" / "fast-forward, summarize" control, currently buried in implicit prompting |
| 9 | **Persistent steering note (Author's Note style)** | Reactive `((OOC))` only nudges once; tone drifts back | **Medium** | **Low–Medium** | Injected every turn at a fixed depth until cleared, vs. one-shot OOC reply |
| 10 | **Regenerate-with-a-directive** | No way to redirect a bad draft without a full swipe UI | **Medium** | **Low** | "Reroll — shorter" / "reroll — less exposition"; lighter than full swipes |
| 11 | **Suggest-my-move / impersonate-me** | Player writer's-block stalls momentum | **Low–Medium** | **Low–Medium** | AI drafts a suggested player action/line to edit or discard |
| 12 | **Swipes + inline edit + streaming** | No way to pick among drafts or fix a bad line in place | **High** (control, not intrinsic quality) | **High** | Already flagged as a known, deferred gap in the two-tier hub spec; biggest lift, biggest interaction-model change |
| 13 | **Player-selectable narration model/voice** | "I don't like this model's prose style" is really a model-choice problem | **Medium** | **Medium** | You already have role-based provider config; this exposes it per-session to the player instead of only an operator |
| 14 | **Rewind-and-fork / timeline branching** | Can't back up several turns when a whole direction went wrong | **Medium–High** | **High** | Needs branch-aware turn storage instead of linear scene history; biggest data-model change on this list |

## Recommended sequencing

Given the stated goal is **quality + NPC feel** specifically (not general
UX), rank by that axis first, effort second:

1. **#1 NPC relationship memory wiring** — highest NPC-feel impact, and the
   verified finding above means it's mostly plumbing, not new design.
2. **#2 Per-NPC voice anchors** — pairs naturally with #1 (same `npc_profile`
   document could carry both relationship state and voice-anchor lines),
   compounds the "NPCs feel distinct and remember me" effect.
3. **#3 Anti-repetition list** — cheapest quality win on the list, unrelated
   to the other two, can land in parallel.
4. Everything else in the table is control/interaction-model work
   (steering, regen, model choice, branching, swipes) — valuable, but
   secondary to the stated NPC-feel/quality goal and better sequenced after
   1–3 land and get evaluated against real play.

## Open questions before starting #1

- Does `context_assembly.assemble()` already know which NPCs are "in scene"
  in a form cheap to map to `npc_profile.entity_id`, or does that require a
  new lookup?
- Should the relationship snapshot affect only the actor-block context (GM
  reads it, decides how to portray the NPC) or also feed `gm_awareness`/tool
  routing (e.g., a hostile-stance NPC biases toward `contested` rolls)?
  Recommend starting read-only (context only) to keep the first cut small.
