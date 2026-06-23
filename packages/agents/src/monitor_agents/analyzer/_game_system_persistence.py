"""
Build and persist game system data structures from raw LLM extraction results.

This module contains the free function ``save_game_system`` which transforms
raw dicts from LLM extraction calls into typed Pydantic models and persists
them to MongoDB.
"""

from __future__ import annotations

import structlog
from typing import Any, Callable, Dict, List, Optional, Tuple, TypeVar
from uuid import UUID

from monitor_data.schemas.game_systems import (
    AbilityScoreGeneration,
    AbilityScoreMethod,
    AdvancementSystem,
    AttributeDefinition,
    Background,
    CharacterCreationProcedure,
    ConditionDefinition,
    CoreMechanic,
    CoreMechanicType,
    CreationLogicStep,
    CreationStep,
    CreationStepType,
    GameRule,
    GameRuleType,
    GameSystemCreate,
    LogicStepType,
    NPCAttack,
    NPCCreationRules,
    NPCStatBlock,
    NPCTier,
    ResolutionMechanic,
    ResourceDefinition,
    SceneryRule,
    SkillDefinition,
    StartingPackage,
    SuccessDegree,
    SuccessType,
)
from monitor_data.schemas.knowledge_packs import (
    EmbeddedGameSystem,
    ExtractedAgenda,
    ExtractedCharacterProfile,
    ExtractedGenerationTemplate,
    ExtractedRandomTable,
    ExtractedTopology,
)
from monitor_data.schemas.random_tables import RandomTableCreate, RandomTableEntry
from monitor_data.tools.mongodb_tools import (
    mongodb_create_game_system,
    mongodb_create_random_table,
)

logger = structlog.get_logger(__name__)

T = TypeVar("T")


def _build_random_tables(
    tables: List[ExtractedRandomTable],
) -> List[UUID]:
    """Persist extracted random tables to MongoDB and return their IDs."""
    table_ids: List[UUID] = []
    for t in tables:
        try:
            entries = [
                RandomTableEntry(
                    min_roll=e.min_roll,
                    max_roll=e.max_roll,
                    value=e.value,
                    subtable_name=e.subtable_name,
                )
                for e in t.entries
            ]
            created = mongodb_create_random_table(
                RandomTableCreate(
                    name=t.name,
                    description=t.description,
                    dice_formula=t.dice_formula,
                    table_type=t.table_type,
                    entries=entries,
                )
            )
            table_ids.append(created.id)
        except Exception as exc:
            logger.warning("Failed to persist extracted random table '%s': %s", t.name, exc)
    return table_ids


def _build_typed_rules(game_rules: List[Dict[str, Any]]) -> List[GameRule]:
    """Convert raw rule dicts into typed GameRule objects."""
    typed_rules: List[GameRule] = []
    for r in game_rules:
        if isinstance(r, GameRule):
            typed_rules.append(r)
            continue
        try:
            rule_type = GameRuleType(r.get("rule_type", "custom").lower())
        except ValueError:
            rule_type = GameRuleType.CUSTOM
        typed_rules.append(
            GameRule(
                name=r.get("name", "Unknown Rule")[:200],
                rule_type=rule_type,
                description=r.get("description", "")[:1000],
                formula=r.get("formula"),
                source_ref=r.get("source_ref"),
                tags=r.get("tags", []),
            )
        )
    return typed_rules


def _build_typed_list(
    raw_items: List[Any],
    expected_type: type[T],
    builder: Callable[[Dict[str, Any]], T],
) -> List[T]:
    """Build a typed list from raw dicts, skipping invalid items silently.

    Args:
        raw_items: List of raw items (dicts or already-typed objects)
        expected_type: The expected Pydantic model type
        builder: Function that converts a dict to the typed object

    Returns:
        List of successfully built typed objects
    """
    result: List[T] = []
    for item in raw_items:
        if isinstance(item, expected_type):
            result.append(item)
            continue
        if not isinstance(item, dict):
            continue
        try:
            result.append(builder(item))
        except Exception:
            continue
    return result


def _build_attributes(charsheet_data: Dict[str, Any]) -> List[AttributeDefinition]:
    """Extract and validate attribute definitions from raw charsheet data."""

    def builder(a: Dict[str, Any]) -> AttributeDefinition:
        return AttributeDefinition(
            name=a["name"][:100],
            abbreviation=a.get("abbreviation", a["name"][:10])[:10],
            min_value=int(a.get("min_value", 1)),
            max_value=int(a.get("max_value", 20)),
            default_value=int(a.get("default_value", 10)),
            modifier_formula=a.get("modifier_formula"),
        )

    return _build_typed_list(charsheet_data.get("attributes", []), AttributeDefinition, builder)


def _build_skills(charsheet_data: Dict[str, Any]) -> List[SkillDefinition]:
    """Extract and validate skill definitions from raw charsheet data."""

    def builder(s: Dict[str, Any]) -> SkillDefinition:
        return SkillDefinition(
            name=s["name"][:100],
            abbreviation=s.get("abbreviation"),
            linked_attribute=s.get("linked_attribute"),
            description=s.get("description"),
        )

    return _build_typed_list(charsheet_data.get("skills", []), SkillDefinition, builder)


def _build_resources(charsheet_data: Dict[str, Any]) -> List[ResourceDefinition]:
    """Extract and validate resource definitions from raw charsheet data."""

    def builder(r: Dict[str, Any]) -> ResourceDefinition:
        return ResourceDefinition(
            name=r["name"][:100],
            abbreviation=r.get("abbreviation", r["name"][:10])[:10],
            calculation=r.get("calculation"),
            min_value=int(r.get("min_value", 0)),
            recovers_on=r.get("recovers_on"),
            depleted_effect=r.get("depleted_effect"),
        )

    return _build_typed_list(charsheet_data.get("resources", []), ResourceDefinition, builder)


def _build_conditions(charsheet_data: Dict[str, Any]) -> List[ConditionDefinition]:
    """Extract and validate condition definitions from raw charsheet data."""


    def builder(c: Dict[str, Any]) -> ConditionDefinition:
        return ConditionDefinition(
            name=c["name"][:100],
            description=c.get("description"),
            roll_modifier=int(c["roll_modifier"]) if c.get("roll_modifier") is not None else None,
            roll_mode_override=c.get("roll_mode_override"),
        )

    return _build_typed_list(charsheet_data.get("conditions", []), ConditionDefinition, builder)


def _build_scenery_rules(charsheet_data: Dict[str, Any]) -> List[SceneryRule]:
    """Extract and validate scenery rules from raw charsheet data."""

    def builder(s: Dict[str, Any]) -> SceneryRule:
        return SceneryRule(
            keyword=s["keyword"][:100],
            trigger_verbs=s.get("trigger_verbs", []),
            roll_modifier=int(s["roll_modifier"]) if s.get("roll_modifier") is not None else None,
            roll_mode_override=s.get("roll_mode_override"),
            reason_text=s.get("reason_text"),
        )

    return _build_typed_list(charsheet_data.get("scenery_rules", []), SceneryRule, builder)


def _build_core_mechanic(charsheet_data: Dict[str, Any]) -> CoreMechanic:
    """Build core mechanic from extracted data or sensible defaults."""
    cm_data = charsheet_data.get("core_mechanic")
    if isinstance(cm_data, CoreMechanic):
        return cm_data

    cm_data = cm_data or {}
    try:
        cm_type = CoreMechanicType(cm_data.get("type", "d20").lower())
    except ValueError:
        cm_type = CoreMechanicType.D20
    try:
        cm_success = SuccessType(cm_data.get("success_type", "meet_or_beat").lower())
    except ValueError:
        cm_success = SuccessType.MEET_OR_BEAT
    return CoreMechanic(
        type=cm_type,
        formula=cm_data.get("formula", "Auto-detected — review and correct as needed")[:200],
        success_type=cm_success,
    )


def _merge_powers_and_subsystems(
    typed_rules: List[GameRule],
    charsheet_data: Dict[str, Any],
    system_name: str,
) -> List[GameRule]:
    """Merge power/subsystem entries from charsheet into typed rules (deduped)."""
    existing_rule_names = {rule.name.lower().strip() for rule in typed_rules}

    for power in charsheet_data.get("powers", []):
        name = str(power.get("name", "")).strip()
        if not name or name.lower() in existing_rule_names:
            continue
        category = str(power.get("category", "power")).strip() or "power"
        description = (
            str(power.get("description", "")).strip()
            or f"{name} is a named {category} in {system_name}."
        )
        typed_rules.append(
            GameRule(
                name=name[:200],
                rule_type=GameRuleType.CUSTOM,
                description=f"{category.title()} option: {description}"[:2000],
                formula=None,
                source_ref=None,
                tags=["subsystem", f"power:{category.lower().replace(' ', '_')}"],
            )
        )
        existing_rule_names.add(name.lower())

    for subsystem in charsheet_data.get("subsystems", []):
        name = str(subsystem.get("name", "")).strip()
        if not name or name.lower() in existing_rule_names:
            continue
        scope = str(subsystem.get("scope", "custom")).strip() or "custom"
        description = (
            str(subsystem.get("description", "")).strip()
            or f"{name} is a named subsystem in {system_name}."
        )
        typed_rules.append(
            GameRule(
                name=name[:200],
                rule_type=GameRuleType.CUSTOM,
                description=f"Subsystem ({scope}): {description}"[:2000],
                formula=None,
                source_ref=None,
                tags=["subsystem", f"scope:{scope.lower().replace(' ', '_')}"],
            )
        )
        existing_rule_names.add(name.lower())

    return typed_rules


def _build_character_creation(
    creation_procedure_data: Dict[str, Any],
) -> Optional[CharacterCreationProcedure]:
    """Build character creation procedure from extracted data."""
    if not creation_procedure_data.get("steps") and not creation_procedure_data.get(
        "ability_score_generation"
    ):
        return None

    # Build creation steps
    creation_steps: List[CreationStep] = []
    for s in creation_procedure_data.get("steps", []):
        if isinstance(s, CreationStep):
            creation_steps.append(s)
            continue
        try:
            step_type = CreationStepType(s.get("step_type", "custom"))
        except ValueError:
            step_type = CreationStepType.CUSTOM
        creation_steps.append(
            CreationStep(
                step_number=int(s.get("step_number", len(creation_steps) + 1)),
                step_type=step_type,
                title=str(s.get("title", ""))[:200],
                instructions=str(s.get("instructions", ""))[:2000],
                is_optional=bool(s.get("is_optional", False)),
                options=[str(o)[:200] for o in s.get("options", [])],
            )
        )

    # Build creation logic
    creation_logic: List[CreationLogicStep] = []
    for logic_entry in creation_procedure_data.get("logic", []):
        if isinstance(logic_entry, CreationLogicStep):
            creation_logic.append(logic_entry)
            continue
        try:
            logic_type = LogicStepType(logic_entry.get("logic_type", "choice"))
        except ValueError:
            logic_type = LogicStepType.CHOICE
        creation_logic.append(
            CreationLogicStep(
                step_number=int(logic_entry.get("step_number", 1)),
                logic_type=logic_type,
                data_source=logic_entry.get("data_source"),
                target_field=logic_entry.get("target_field"),
                prompt_template=logic_entry.get("prompt_template"),
                is_automated=bool(logic_entry.get("is_automated", False)),
            )
        )

    # Build ability score generation
    ability_score_gen: Optional[AbilityScoreGeneration] = None
    ag_data = creation_procedure_data.get("ability_score_generation", {})
    if ag_data and ag_data.get("method"):
        try:
            ag_method = AbilityScoreMethod(ag_data["method"])
        except ValueError:
            ag_method = AbilityScoreMethod.FREE_ASSIGN
        ability_score_gen = AbilityScoreGeneration(
            method=ag_method,
            roll_formula=ag_data.get("roll_formula"),
            roll_count=ag_data.get("roll_count"),
            point_budget=ag_data.get("point_budget"),
            standard_array=ag_data.get("standard_array", []),
            min_score=ag_data.get("min_score"),
            max_score=ag_data.get("max_score"),
        )

    # Build backgrounds
    creation_backgrounds: List[Background] = [
        Background(
            name=str(bg.get("name", ""))[:200],
            description=str(bg.get("description", ""))[:1000],
            skill_proficiencies=bg.get("skill_proficiencies", []),
            equipment=bg.get("equipment", []),
        )
        for bg in creation_procedure_data.get("backgrounds", [])
    ]

    # Build starting packages
    creation_packages: List[StartingPackage] = [
        StartingPackage(
            name=str(pkg.get("name", ""))[:200],
            class_or_archetype=pkg.get("class_or_archetype"),
            items=pkg.get("items", []),
            gold=int(pkg.get("gold", 0)),
            notes=pkg.get("notes"),
        )
        for pkg in creation_procedure_data.get("starting_packages", [])
    ]

    # Build advancement system
    advancement: Optional[AdvancementSystem] = None
    adv_data = creation_procedure_data.get("advancement", {})
    if adv_data and adv_data.get("method"):
        advancement = AdvancementSystem(
            method=str(adv_data["method"])[:100],
            max_level=adv_data.get("max_level"),
            milestone_description=adv_data.get("description"),
        )

    return CharacterCreationProcedure(
        steps=creation_steps,
        logic=creation_logic,
        ability_score_generation=ability_score_gen,
        backgrounds=creation_backgrounds,
        starting_packages=creation_packages,
        advancement=advancement,
    )


def _build_npc_stat_blocks(npc_data: Dict[str, Any]) -> List[NPCStatBlock]:
    """Build NPC stat blocks from raw extraction data."""
    npc_stat_blocks: List[NPCStatBlock] = []
    for block in npc_data.get("stat_blocks", []):
        if isinstance(block, NPCStatBlock):
            npc_stat_blocks.append(block)
            continue
        try:
            tier = NPCTier(block.get("tier", "standard"))
        except ValueError:
            tier = NPCTier.STANDARD
        attacks = [
            NPCAttack(
                name=a.get("name", "Attack")[:200],
                damage=a.get("damage", "")[:100],
            )
            for a in block.get("attacks", [])
        ]
        npc_stat_blocks.append(
            NPCStatBlock(
                name=block.get("name", "Unknown NPC")[:200],
                tier=tier,
                hp=int(block.get("hp", 0)) if block.get("hp") is not None else None,
                defense=str(block["defense"]) if block.get("defense") else None,
                attacks=attacks,
                special_abilities=block.get("special_abilities", []),
                source_ref=block.get("source_ref"),
            )
        )
    return npc_stat_blocks


def _build_npc_creation_rules(npc_data: Dict[str, Any]) -> Optional[NPCCreationRules]:
    """Build NPC creation rules from raw extraction data."""
    raw_cr = npc_data.get("creation_rules")
    if not raw_cr:
        return None
    if isinstance(raw_cr, NPCCreationRules):
        return raw_cr
    return NPCCreationRules(
        types_available=raw_cr.get("types_available", []),
        simplified_stat_method=raw_cr.get("simplified_stat_method"),
        scaling_notes=raw_cr.get("scaling_notes"),
    )


def _build_resolution_mechanics(raw_mechanics: List[Dict[str, Any]]) -> List[ResolutionMechanic]:
    """Extract and validate detailed resolution mechanics from raw extraction data."""

    def builder(rm: Dict[str, Any]) -> ResolutionMechanic:
        # Build success degrees
        degrees = [
            SuccessDegree(
                threshold=str(d.get("threshold", "1"))[:200],
                label=str(d.get("label", "success"))[:100],
                effect=str(d.get("effect", ""))[:500],
            )
            for d in rm.get("success_degrees", [])
            if isinstance(d, dict)
        ]

        try:
            m_type = CoreMechanicType(str(rm.get("mechanic_type", "d20")).lower())
        except ValueError:
            m_type = CoreMechanicType.D20

        try:
            s_type = SuccessType(str(rm.get("success_type", "meet_or_beat")).lower())
        except ValueError:
            s_type = SuccessType.MEET_OR_BEAT

        return ResolutionMechanic(
            dice_formula=str(rm.get("dice_formula", "1d20"))[:200],
            mechanic_type=m_type,
            difficulty_model=str(rm.get("difficulty_model", "fixed_dc"))[:50],
            difficulty_range=rm.get("difficulty_range"),
            success_degrees=degrees,
            success_type=s_type,
            critical_success=rm.get("critical_success"),
            critical_failure=rm.get("critical_failure"),
            consequence_on_failure=rm.get("consequence_on_failure"),
            complication_mechanic=rm.get("complication_mechanic"),
        )

    return _build_typed_list(raw_mechanics, ResolutionMechanic, builder)


async def save_game_system(
    system_name: str,
    game_rules: List[Dict[str, Any]],
    source_name: str,
    charsheet_data: Optional[Dict[str, Any]] = None,
    creation_procedure_data: Optional[Dict[str, Any]] = None,
    npc_data: Optional[Dict[str, Any]] = None,
    random_tables: Optional[List[ExtractedRandomTable]] = None,
    agendas: Optional[List[ExtractedAgenda]] = None,
    topologies: Optional[List[ExtractedTopology]] = None,
    character_profiles: Optional[List[ExtractedCharacterProfile]] = None,
    generation_templates: Optional[List[ExtractedGenerationTemplate]] = None,
    resolution_mechanics: Optional[List[Dict[str, Any]]] = None,
    source_document_id: Optional[UUID] = None,
) -> Tuple[Optional[UUID], EmbeddedGameSystem]:
    """
    Save extracted game system to MongoDB and return (id, EmbeddedGameSystem).

    Returns a 2-tuple so the caller can store the embedded copy on the
    KnowledgePack AND keep the reference ID for the ``game_systems``
    collection.
    """
    from monitor_agents.utils.analyzer_support import (
        filter_player_attributes,
        filter_player_skills,
        filter_player_resources,
    )

    charsheet_data = charsheet_data or {}
    creation_procedure_data = creation_procedure_data or {}
    npc_data = npc_data or {}

    # Build typed components
    typed_rules = _build_typed_rules(game_rules)
    attributes = _build_attributes(charsheet_data)
    skills = _build_skills(charsheet_data)
    resources = _build_resources(charsheet_data)
    conditions = _build_conditions(charsheet_data)
    scenery_rules = _build_scenery_rules(charsheet_data)

    # Apply post-extraction filters
    attributes = filter_player_attributes(attributes)
    skills = filter_player_skills(skills)
    resources = filter_player_resources(resources)

    # Merge powers/subsystems into rules
    typed_rules = _merge_powers_and_subsystems(typed_rules, charsheet_data, system_name)

    # Build core mechanic
    core_mechanic = _build_core_mechanic(charsheet_data)

    # Build resolution mechanics
    resolution_mechanics_list = _build_resolution_mechanics(resolution_mechanics or [])

    # Build character creation procedure
    character_creation = _build_character_creation(creation_procedure_data)

    # Build NPC components
    npc_stat_blocks = _build_npc_stat_blocks(npc_data)
    npc_creation_rules = _build_npc_creation_rules(npc_data)

    # Build and persist random tables
    table_ids = _build_random_tables(random_tables or [])

    # Build embedded copy
    embedded = EmbeddedGameSystem(
        name=system_name,
        description=f"Extracted from {source_name}",
        core_mechanic=core_mechanic,
        attributes=attributes,
        skills=skills,
        resources=resources,
        conditions=conditions,
        scenery_rules=scenery_rules,
        rules=typed_rules,
        character_creation=character_creation,
        npc_stat_blocks=npc_stat_blocks,
        npc_creation_rules=npc_creation_rules,
        random_tables=random_tables or [],
        agendas=agendas or [],
        topologies=topologies or [],
        character_profiles=character_profiles or [],
        generation_templates=generation_templates or [],
        resolution_mechanics=resolution_mechanics_list,
    )

    try:
        system = mongodb_create_game_system(
            GameSystemCreate(
                name=system_name,
                description=f"Extracted from {source_name}",
                core_mechanic=core_mechanic,
                attributes=attributes,
                skills=skills,
                resources=resources,
                conditions=conditions,
                scenery_rules=scenery_rules,
                rules=typed_rules,
                agendas=agendas or [],
                topologies=topologies or [],
                character_profiles=character_profiles or [],
                generation_templates=generation_templates or [],
                character_creation=character_creation,
                npc_stat_blocks=npc_stat_blocks,
                npc_creation_rules=npc_creation_rules,
                random_tables=table_ids,
                resolution_mechanics=resolution_mechanics_list,
                source_document_id=source_document_id,
            )
        )
        return system.id, embedded
    except Exception as exc:
        logger.warning("Failed to save game system '%s': %s", system_name, exc)
        # Still return the embedded data even if the separate collection
        # write failed — the pack itself carries the system regardless.
        return None, embedded
