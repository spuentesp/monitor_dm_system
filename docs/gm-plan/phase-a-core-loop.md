## Phase A — Core Loop Completion (3 weeks)

> **Delivers:** Complete story arc from campaign start to multi-scene play with combat.

### A.1 Complete StoryLoop

**Why:** StoryLoop is the campaign backbone. Without it, sessions are isolated scenes with no arc.

| Task | File(s) | Details |
|------|---------|---------|
| Real `run_scene` node | `loops/story_loop.py` | Delegate to `SceneLoop.run()` — currently stub returns `{"scenes_completed": count}`. Must: (1) instantiate `SceneLoop` with scene params, (2) pass user input through, (3) collect narrative output and proposals |
| Arc evaluation node | `loops/story_loop.py` | New node `evaluate_arc()` between scenes. Uses DSPy to classify: `"rising_action" \| "climax" \| "falling_action" \| "resolution" \| "new_thread"`. Input: completed scenes, world state, pending threads. Output: arc_label, tension_score (0-1), suggested_next_type |
| Intelligent transition | `loops/story_loop.py` | `transition_scene()` must use arc evaluation to decide next scene type. Not just "create next scene" — must propose: `action \| dialogue \| exploration \| rest \| combat \| revelation`. Pass to ContextAssembly for setup |
| `finalize_story` node | `loops/story_loop.py` | Story wrap-up: (1) CanonKeeper commits all pending proposals, (2) generate story summary via DSPy, (3) persist summary to MongoDB story document, (4) update entity states in Neo4j |
| StoryState extensions | `loops/story_loop.py` | Add fields: `arc_label: str`, `tension_score: float`, `active_threads: List[str]`, `completed_threads: List[str]`, `next_scene_type: Optional[str]` |
| Multi-scene test | `tests/e2e/test_story_loop.py` | Test: create universe → start story → complete 3 scenes → verify arc progression and thread tracking |

**Graph target:**
```
init_story → run_scene → evaluate_arc → transition → [run_scene | finalize_story]
```

**Success criteria:**
- [ ] `StoryLoop.start_or_resume()` creates first scene and delegates to SceneLoop
- [ ] Arc evaluation produces meaningful labels across 3+ scenes
- [ ] Scene transitions propose appropriate next scene types
- [ ] `finalize_story` generates a coherent campaign summary
- [ ] Multi-scene E2E test passes

### A.2 Combat Sub-System

**Why:** Combat is the most common TTRPG scenario currently handled ad-hoc by Resolver with `action_type="combat"`. No initiative, no turn order, no opposed checks.

| Task | File(s) | Details |
|------|---------|---------|
| Combat sub-graph | `loops/combat_loop.py` (NEW) | LangGraph `StateGraph` with: `roll_initiative → choose_combatant → resolve_action → check_victory → [next_combatant \| end_combat]` |
| CombatState schema | `loops/combat_loop.py` (NEW) | Fields: `scene_id`, `combatants: List[CombatantState]`, `initiative_order: List[str]`, `current_turn_index: int`, `round_number: int`, `combat_log: List[Dict]`, `pending_proposals`, `combat_active: bool` |
| Initiative system | `loops/combat_loop.py` | `roll_initiative()` — query GameSystemRuntime for initiative stat name, roll per combatant, sort. If no game system: fallback to DEX |
| Opposed checks | `resolver.py` | New resolution mode: `resolution_type="opposed"`. Two actors roll against each other. Higher result wins. Margin determines degree. Add `_resolve_opposed_check(attacker, defender, stat)` |
| Advantage/disadvantage | `resolver.py` | Add `roll_mode: "normal" \| "advantage" \| "disadvantage"` to ResolverOutcome. Roll 2d20 keep highest/lowest. Integrate with GameSystemRuntime for system-specific rules |
| Resource tracking | `game_system.py` | `track_resource(entity_id, resource_name, delta)` — HP, MP, uses-per-rest, etc. Query from MongoDB working state, update after each combat action |
| Combat integration | `scene_loop.py` | Add conditional edge after `resolve_action`: if `action_type == "combat"`, route to CombatLoop instead of straight `narrate`. CombatLoop returns control to SceneLoop when `combat_active == False` |
| Combat narration | `narrator.py` | `_format_combat_context()` helper — formats initiative order, current combatant, recent hits/misses into compact combat state for Narrator |

**Combat graph:**
```
roll_initiative → choose_combatant → resolve_action → narrate_combat → check_victory
                                                                      ↓
                                                         [next_combatant | end_combat → return to SceneLoop]
```

**Success criteria:**
- [ ] 2-party combat runs through initiative → action → resolution → narration
- [ ] Opposed checks produce attacker vs defender results with margin
- [ ] Advantage/disadvantage rolls correctly (2d20 keep highest/lowest)
- [ ] Combat integrates into SceneLoop flow without breaking non-combat turns
- [ ] Resource tracking persists HP changes across combat rounds

### A.3 Multi-Entity Interactions

**Why:** Current system assumes single actor per turn. Real sessions involve NPCs reacting, party members acting, and world events occurring.

| Task | File(s) | Details |
|------|---------|---------|
| Multi-actor turns | `resolver.py` | Support `additional_actors: List[Dict]` in resolve_turn. Each actor gets a mini-resolution. NPC reactions use NPCVoice for dialogue, Resolver for mechanics |
| Party mode | `scene_loop.py` | SceneState gains `party_members: List[UUID]`. On each turn, after player action, each party member gets a reactive micro-turn (1 sentence + possible roll) |
| World events | `scene_loop.py` | New node `check_world_events()` between `narrate` and `persist`. Uses DSPy to determine if a world event should fire based on: tension_score, turns_count, arc_label, pending_threads. If yes: generate event, inject as additional narrative |
| NPC reaction system | `npc_voice.py` | `react_to_action(action, npc_profile, relationship)` — short reactive response (1-2 sentences) without full dialogue generation. For combat: "The guard staggers back" style |

**Success criteria:**
- [ ] NPCs react to player actions within the same turn
- [ ] Party members contribute micro-actions during combat
- [ ] World events fire based on tension/arc context
- [ ] Multi-actor resolution produces coherent narrative

---

