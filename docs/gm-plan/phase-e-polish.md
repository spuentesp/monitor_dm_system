## Phase E — Professional Polish (3 weeks)

> **Delivers:** Character advancement. Frontend completion. Test coverage. CI.

### E.1 Character Advancement

**Why:** Characters are created but never grow. No XP, no leveling, no skill progression.

| Task | File(s) | Details |
|------|---------|---------|
| XP system | `game_system.py` | `award_xp(entity_id, amount, reason)` — track XP per entity in MongoDB. Reasons: "combat_victory", "roleplay_excellence", "skill_use", "story_milestone" |
| Level-up logic | `game_system.py` | `check_level_up(entity_id)` — query game system schema for level thresholds. If XP crosses threshold: propose level-up with stat increases, new abilities |
| Level-up proposals | `canonkeeper.py` | Level-up changes go through CanonKeeper as proposals. Display to player for confirmation before committing |
| Advancement runtime | `game_system.py` | `apply_advancement(entity_id, advancement)` — update character sheet: stats, abilities, resources. Persist to MongoDB |
| Session-end XP summary | `scene_loop.py` | At `finalize_story`, calculate XP earned: per-turn contributions + story milestone bonuses. Present summary to player |

**Success criteria:**
- [ ] XP accumulates across sessions
- [ ] Level-up triggers automatically when threshold crossed
- [ ] Player confirms level-up before stats change
- [ ] Advancement persisted and visible in character sheet

### E.2 Frontend Completion

**Why:** Frontend at ~60%. Many views are placeholders.

| Task | File(s) | Details |
|------|---------|---------|
| Character sheet view | `packages/ui/frontend/` | Display full character sheet: stats, skills, equipment, XP, level. Editable for co-pilot mode |
| Combat tracker UI | `packages/ui/frontend/` | Show initiative order, current combatant, HP bars, round counter. Interactive: click to advance turn |
| World map/entity browser | `packages/ui/frontend/` | Visual entity browser with relationship graph (D3 or similar). Filter by type, domain, relationship |
| Session history view | `packages/ui/frontend/` | Scrollable session log with turn-by-turn display. Highlight key moments (critical hits, story beats) |
| Prep generator UI | `packages/ui/frontend/` | Input: session notes. Output: generated prep material. Save/edit/share |
| GM control panel UI | `packages/ui/frontend/` | Wire up to backend APIs from Phase D.2: entity browser, proposal queue, canon trigger |

**Success criteria:**
- [ ] Character sheet displays correctly and updates after advancement
- [ ] Combat tracker shows real-time initiative and HP
- [ ] Entity browser renders relationship graph
- [ ] Session history is browsable
- [ ] GM control panel is functional

### E.3 Test Coverage & CI

**Why:** Tests at ~20%. No CI pipeline. Changes can break without detection.

| Task | File(s) | Details |
|------|---------|---------|
| Unit test expansion | `packages/*/tests/` | Target: >80% coverage for data-layer, >70% for agents, >60% for cli |
| Combat loop tests | `tests/test_combat_loop.py` | Test: initiative ordering, opposed checks, advantage/disadvantage, resource tracking, victory conditions |
| Story loop tests | `tests/test_story_loop.py` | Test: arc evaluation, scene transitions, thread tracking, multi-scene flow |
| World tick tests | `tests/test_world_tick.py` | Test: faction AI, cascading consequences, CanonKeeper integration |
| Co-pilot mode tests | `tests/test_copilot.py` | Test: session recording, continuity checker, prep generator |
| CI pipeline | `.github/workflows/` | GitHub Actions: lint (ruff) → type check (mypy) → unit tests → E2E tests (with Docker services) |
| Layer boundary check | `scripts/check_layer_dependencies.py` | Add to CI: fail if skip-layer import detected |

**Success criteria:**
- [ ] >200 unit tests passing
- [ ] All new features have dedicated test files
- [ ] CI runs on every PR
- [ ] Layer boundary violations caught automatically

---

