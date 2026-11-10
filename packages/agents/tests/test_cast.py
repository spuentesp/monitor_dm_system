"""Cast model, builder, registry and who-knows-what filtering (Phase 4 Task 1/8)."""

from __future__ import annotations

from uuid import uuid4

from monitor_agents.cast import (
    AGENCY_RULE,
    Cast,
    CastMember,
    build_cast,
    cast_from_state,
    clear_scene_cast,
    fact_visible_to,
    filter_visible_facts,
    get_scene_cast,
    register_scene_cast,
)


class TestBuildCast:
    def test_user_characters_come_first_with_speaker_marked(self):
        cast = build_cast(
            controlled_ids=["a", "b"],
            speaker_id="b",
            entity_context=[
                {"id": "a", "name": "Ana", "entity_type": "character"},
                {"id": "b", "name": "Bor", "entity_type": "character"},
                {"id": "n1", "name": "Vex", "entity_type": "character"},
            ],
            scene_id="s1",
        )
        assert [m.entity_id for m in cast.members] == ["a", "b", "n1"]
        assert cast.members[0].controller == "user"
        assert cast.members[1].is_speaker is True
        assert cast.members[0].is_speaker is False
        assert cast.members[2].controller == "gm"

    def test_persona_link_shown_on_user_characters(self):
        cast = build_cast(
            controlled_ids=["a"],
            speaker_id="a",
            personas={"a": {"persona_id": "p1", "persona_name": "Ana Persona"}},
        )
        member = cast.by_id("a")
        assert member is not None
        assert member.persona_id == "p1"
        assert member.persona_name == "Ana Persona"

    def test_speaker_outside_roster_is_user_controlled(self):
        cast = build_cast(controlled_ids=[], speaker_id="pc-9", actor_context={"id": "pc-9", "name": "Solo"})
        member = cast.by_id("pc-9")
        assert member is not None
        assert member.controller == "user"
        assert member.is_speaker is True
        assert member.name == "Solo"

    def test_npc_profiles_supply_gm_members(self):
        cast = build_cast(
            controlled_ids=["a"],
            speaker_id="a",
            npc_profiles={"n1": {"name": "Old Tomas"}},
        )
        member = cast.by_id("n1")
        assert member is not None
        assert member.controller == "gm"
        assert member.name == "Old Tomas"

    def test_party_record_adds_missing_members(self):
        cast = build_cast(
            controlled_ids=["a"],
            speaker_id="a",
            party={"members": [{"id": "a", "name": "Ana"}, {"id": "n9", "name": "Guide", "role": "npc"}]},
        )
        assert cast.by_id("n9") is not None
        assert cast.by_id("n9").controller == "gm"

    def test_witness_ids_cover_the_whole_cast(self):
        cast = build_cast(controlled_ids=["a"], speaker_id="a", npc_profiles={"n1": {"name": "Vex"}})
        assert set(cast.witness_ids()) == {"a", "n1"}


class TestPromptBlock:
    def test_block_carries_agency_rule_and_markers(self):
        cast = build_cast(
            controlled_ids=["a", "b"],
            speaker_id="a",
            entity_context=[{"id": "n1", "name": "Vex", "entity_type": "character"}],
        )
        block = cast.to_prompt_block()
        assert "[PLAYER-CONTROLLED] Ana" in block or "[PLAYER-CONTROLLED] a" in block
        assert "(SPEAKING NOW)" in block
        assert "[GM-CONTROLLED] Vex" in block
        assert AGENCY_RULE in block
        assert "NEVER" in AGENCY_RULE

    def test_empty_cast_renders_nothing(self):
        assert Cast().to_prompt_block() == ""


class TestFactVisibility:
    def test_no_witness_record_is_common_knowledge(self):
        assert fact_visible_to({"statement": "ingested lore"}, "n1") is True

    def test_witnessed_fact_hidden_from_absent_npc(self):
        fact = {"statement": "the ledger vanished", "witnesses": ["a", "b"]}
        assert fact_visible_to(fact, "n1") is False
        assert fact_visible_to(fact, "a") is True

    def test_told_fact_is_visible(self):
        fact = {"statement": "x", "witnesses": ["a"], "told_to": ["n1"]}
        assert fact_visible_to(fact, "n1") is True

    def test_common_knowledge_marker_wins(self):
        fact = {"statement": "x", "witnesses": ["a"], "properties": {"common_knowledge": True}}
        assert fact_visible_to(fact, "n1") is True

    def test_proposal_content_carrier(self):
        fact = {"content": {"statement": "x", "witnesses": ["a"]}}
        assert fact_visible_to(fact, "n1") is False

    def test_filter_visible_facts(self):
        facts = [
            {"statement": "common", "witnesses": []},
            {"statement": "scene-2 secret", "witnesses": ["a"]},
        ]
        visible = filter_visible_facts(facts, "n1")
        assert [f["statement"] for f in visible] == ["common"]


class TestRegistry:
    def test_register_and_get(self):
        scene_id = str(uuid4())
        cast = build_cast(controlled_ids=["a"], speaker_id="a", scene_id=scene_id)
        register_scene_cast(scene_id, cast)
        assert get_scene_cast(scene_id) is cast
        clear_scene_cast(scene_id)
        assert get_scene_cast(scene_id) is None

    def test_cast_from_state_prefers_registry(self):
        scene_id = str(uuid4())
        cast = build_cast(
            controlled_ids=["a", "b"],
            speaker_id="a",
            entity_context=[{"id": "n1", "name": "Vex", "entity_type": "character"}],
            scene_id=scene_id,
        )
        register_scene_cast(scene_id, cast)

        class _State:
            pass

        state = _State()
        state.scene_id = scene_id
        state.actor_id = "a"
        state.actor_context = {"id": "a", "name": "Ana"}
        state.entity_context = []
        state.npc_profiles = {}
        assert cast_from_state(state) is cast

    def test_cast_from_state_fallback_marks_only_speaker_as_user(self):
        class _State:
            pass

        state = _State()
        state.scene_id = str(uuid4())
        state.actor_id = "pc1"
        state.actor_context = {"id": "pc1", "name": "Ana"}
        state.entity_context = [{"id": "n1", "name": "Vex", "entity_type": "character"}]
        state.npc_profiles = {}
        cast = cast_from_state(state)
        assert cast.by_id("pc1").controller == "user"
        assert cast.by_id("n1").controller == "gm"

    def test_registry_evicts_oldest(self):
        from monitor_agents.cast import _CAST_REGISTRY, _CAST_REGISTRY_MAX

        for i in range(_CAST_REGISTRY_MAX + 2):
            register_scene_cast(f"scene-{i}", Cast(members=[CastMember(entity_id=str(i))]))
        assert len(_CAST_REGISTRY) <= _CAST_REGISTRY_MAX
        assert get_scene_cast("scene-0") is None
