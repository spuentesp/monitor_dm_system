# P-19: Chat-Guided Session Setup and Character Creation

**Actor:** User
**Trigger:** User starts natural-language onboarding in the chat interface at session start

**Purpose:** Allow MONITOR to guide the player conversationally through selecting a setting, choosing or creating a universe, and building one or more PCs — using the normal chat interface.

**Flow (P-19 redesign, 2026-07-29):**
1. User creates a session from `SetupPanel`, deliberately picking (or not picking) a saved PC.
2. If a saved PC was selected, MONITOR skips character creation and goes straight to the setting introduction + Session Zero agreement stage.
3. If no PC was selected, the character interview (renamed from the old character-focused `SessionZeroLoop`) collects the player’s identity, concept, backstory, bonds, fears, and motivations. Mechanical character creation runs immediately after when a rules system is bound; otherwise the player gets a narrative-only PC.
4. A canon-grounded `SessionIntro` is assembled from the universe name, optional `KnowledgePack.intro_text`, and universe-scoped axioms/facts/locations/factions. No cross-universe fallback; sparse universes are marked `unverified`.
5. The compact `StoryAgreementsLoop` asks three questions in order: desired story & PC role, themes & tone/pacing, and lines & veils. Authored prompt collections take precedence over the LLM path.
6. The player must explicitly press **Begin Story** (or “Use defaults & begin” as a Skip-preplay escape hatch). Begin finalizes agreements, bootstraps Story/Scene with the bound PC, copies the agreed premise into the session, and emits the first in-fiction narration.
7. From Begin onward, the session is in `active_play`. Lines and veils are surfaced to both the Resolver and Narrator prompts on every turn.

**Output:** a low-friction onboarding path where MONITOR acts like a real DM guiding setup through chat

### Implementation

**Layer 2 (Agents / runtime):**
- `packages/agents/src/monitor_agents/loops/preplay_orchestrator.py` — LangGraph state machine that owns the new preplay phases (`character_interview`, `char_creation`, `session_zero`).
- `packages/agents/src/monitor_agents/loops/character_interview_loop.py` and `character_interview.py` — character-focused interview (compatibility shim for the old `SessionZeroLoop` name).
- `packages/agents/src/monitor_agents/loops/story_agreements_loop.py` + `story_agreements.py` — compact three-question agreement interview.
- `packages/agents/src/monitor_agents/loops/preplay_finalize.py` — single entry point for `Begin Story`: confirms agreements, copies premise/tone, bootstraps Story/Scene, runs the Narrator opening.
- `packages/agents/src/monitor_agents/setting_intro.py` — canon-grounded setting introduction (pack intro → universe-scoped anchors → fallback).
- `packages/agents/src/monitor_agents/loops/preplay_phases.py` — canonical phase enum + legacy alias normalizer (`awaiting_character` → `character_interview`).
- `packages/agents/src/monitor_agents/loops/preplay_support.py::resolve_authored_questions` — generalized resolver that powers both the character interview and the agreement stage via a category argument.
- `Resolver` and `Narrator` consume a `scene_context["agreements"]` block; `SceneLoop`/`SceneState` carry `agreements_lines` / `agreements_veils`; the GMAgent ReAct signature carries a `table_agreements` directive.

**Layer 3 (UI):**
- `packages/ui/frontend/src/components/play/SetupPanel.tsx` — explicit character selection (no auto-pick of the first PC).
- `packages/ui/frontend/src/components/play/PlayConsole.tsx` — **Begin Story** button when agreements await confirmation; **Use defaults & begin** as the Skip-preplay label.
- `packages/ui/frontend/src/lib/play-constants.ts` — canonical phase styles for `character_interview`, `char_creation`, and `session_zero`.
- `packages/ui/frontend/src/lib/api.ts::chatApi.beginStory` — POST `/api/chat/{id}/begin`.

---
