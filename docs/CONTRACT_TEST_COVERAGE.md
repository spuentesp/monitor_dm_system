# Contract Test Coverage

This document tracks the contract test sweep that completed **Phase 0.2** of `docs/CLOSING_THE_GAP.md`.

## Final State

- **1905 contract + behavior tests passing**, 13 skipped, 16 warnings (no errors)
- **0 layer-dependency violations** (`python scripts/check_layer_dependencies.py` → "All layer dependency checks passed")
- **75+ contract test files** in `tests/contracts/`
- **Scene-end choreography behavior tests** (15 tests) in `tests/behavior/test_scene_end_choreography_behavior.py`
- **E2E suite** (with `RUN_E2E=1`): 81 passed, 55 skipped, 0 failed in 30.89s

## How To Run

```bash
# Run all contract tests
uv run pytest tests/contracts/ -q --tb=no

# Verify layer boundaries
python scripts/check_layer_dependencies.py
```

## Schemas Covered (in this sweep)

| Schema file | Tests | Class count |
|-------------|-------|-------------|
| `character_sheets.py` | 35 | 7 |
| `entity_templates.py` | 47 | 10 |
| `llm_config.py` | 28 | 7 |
| `agent_responses.py` | 23 | 6 |
| `memories.py` | 44 | 10 |
| `resolutions.py` | 49 | 15 |
| `play_sessions.py` | 23 | 6 |
| `ingestion_jobs.py` | 31 | 6 |
| `ingestion_delta.py` | 31 | 4 |
| `npc_profiles.py` | 41 | 6 |
| `pack_completeness.py` | 21 | 3 |
| `npc_dialogues.py` | 36 | 7 |
| `npc_scene_generator.py` | 22 | 4 |
| `generated_narratives.py` | 24 | 5 |
| `vectors.py` | 52 | 19 |

## Test Patterns Established

- Use real Pydantic models, never `MagicMock`
- Test defaults, full construction, required-field errors
- Test numeric bounds (ge/le) and length bounds (max_length, min_length)
- Test enum validation by passing invalid string and confirming `ValidationError`
- Test computed properties (e.g., `IngestionDelta.has_changes`, `.apply_decision`)
- Test `model_validator` normalizers (e.g., `VectorSearchRequest.limit → top_k`)
- `pytestmark = pytest.mark.unit` for fast collection

## Schemas Still Without Dedicated Tests (intentionally skipped)

| Schema | Why skipped |
|--------|-------------|
| `tag_pool.py` | Single dataclass, not Pydantic — covered indirectly by `test_definitions_contracts.py` and `test_tag_registry_contracts.py` |

## Next Steps (Phase 0.3+)

See `docs/CLOSING_THE_GAP.md`. Upcoming phases:

- **0.3** — Investigate and fix E2E test failures
- **0.4** — Scene-end choreography tests
- **1** — Behavior tests for loop pure functions
- **2-3** — World seeding and world management behavior tests
- **4** — GM Assistant tool tests
- **5** — Polish & observability

---

## Phase 0.4 & Phase 2-4 Behavior Test Coverage Update

The plan was extended to also cover loop and agent choreography tests under `tests/behavior/`. These exercise **pure functions** in the agent layer (no LLM, no DB) and prove the choreographed flow logic.

### Behavior Test Files Added

| File | Tests | What it covers |
|------|-------|---------------|
| `test_scene_end_choreography_behavior.py` | 15 | `route_after_narration`, `route_after_resolve`, `SceneState`, `complete_current_scene` |
| `test_world_building_choreography_behavior.py` | 12 | `WorldBuildingState`, `format_response`, `load_world_context` first-turn detection |
| `test_conversation_loop_choreography_behavior.py` | 11 | `_normalize_conversation_change_type` and `ConversationState` |
| `test_combat_loop_choreography_behavior.py` | 24 | `_calculate_modifier_from_attributes`, `_pick_npc_target`, `_find_target_in_action`, `_apply_damage`, `_get_hp`, `_format_combat_context`, `route_after_*`, state defaults |
| `test_story_loop_choreography_behavior.py` | 19 | `_arc_label_to_purpose`, `route_after_scene`, `run_scene`, `StoryState` defaults, scene creation |
| `test_character_creation_loop_choreography_behavior.py` | 52 | `_parse_attribute_assignment`, `_parse_skill_choices`, `_match_option`, `_format_current_attrs`, `_build_completion_message`, routing, all step types, state defaults |
| `test_progression_loop_choreography_behavior.py` | 6 | `load_progression_options`, `finalize_progression` (with mocked CanonKeeper), `ProgressionState` |
| `test_plot_hooks_choreography_behavior.py` | 25 | `_parse_result`, `_heuristic_hooks`, `_heuristic_contradictions`, all Pydantic schemas |
| `test_main_menu_choreography_behavior.py` | 25 | `MenuChoice` enum, `parse_menu_input`, `handle_menu_choice`, `display_menu`, `run_menu_loop` (with mocked input) |
| `test_source_scope_choreography_behavior.py` | 31 | `_as_list`, `_dedupe`, `derive_source_scope`, `append_scope_terms_to_query`, `rank_snippets_with_source_scope` |

**Total: 220 new behavior tests** (462 passing in `tests/behavior/` including earlier files)

### Phase Status

| Phase | Status |
|-------|--------|
| 0.2 — Skipped contract tests | ✅ Complete (1905+ contract tests passing) |
| 0.3 — E2E test failures | ✅ Complete (81 E2E tests passing, 0 failed) |
| 0.4 — Scene-end choreography | ✅ Complete (15 behavior tests) |
| 2-3 — Behavior tests (loops) | ✅ Complete (123 tests across 6 loops) |
| 4 — GM Assistant tool tests | ✅ Complete (81 tests: plot hooks + main menu + source scope) |
| 5 — Polish & observability | ⏳ Pending |
