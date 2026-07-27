"""
Build and persist game system data structures from raw LLM extraction results.

This module contains the free function ``save_game_system`` which transforms
raw dicts from LLM extraction calls into typed Pydantic models and persists
them to MongoDB.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar
from uuid import UUID

import structlog
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
from monitor_data.schemas.knowledge_packs import (  # type: ignore[attr-defined]
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
    tables: list[ExtractedRandomTable],
) -> list[UUID]:
    """Persist extracted random tables to MongoDB and return their IDs."""
    table_ids: list[UUID] = []
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
            table_ids.append(created.id)  # type: ignore[attr-defined]
        except Exception as exc:
            logger.warning("Failed to persist extracted random table '%s': %s", t.name, exc)
    return table_ids


def _build_typed_rules(game_rules: list[dict[str, Any]]) -> list[GameRule]:
    """Convert raw rule dicts into typed GameRule objects.

    The downstream Pydantic model (``GameRule``) also normalizes
    ``rule_type`` via its ``field_validator``, so this function mainly
    exists as a typed-construction helper. We still log when a non-canonical
    alias reaches us here — the upstream validator should have already
    mapped it, so hits indicate either a bypass or a new alias to add.
    """
    typed_rules: list[GameRule] = []
    for r in game_rules:
        if isinstance(r, GameRule):
            typed_rules.append(r)
            continue
        raw_type = (r.get("rule_type") or "custom").lower()
        if raw_type not in {e.value for e in GameRuleType}:
            logger.info(
                "rule_type_alias_hit",
                raw=raw_type,
                rule_name=r.get("name", "Unknown Rule"),
            )
        try:
            rule_type = GameRuleType(raw_type)
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
    raw_items: list[Any],
    expected_type: type[T],
    builder: Callable[[dict[str, Any]], T],
    *,
    label: str = "",
    skipped: list[str] | None = None,
) -> list[T]:
    """Build a typed list from raw dicts.

    Invalid items (non-dict values, builder exceptions) are now logged at
    WARNING level and appended to ``skipped`` (when provided) as short
    ``"<label>: <item-name>: <error>"`` strings. Older versions silently
    dropped both — see INGESTION_PIPELINE_AUDIT.md Finding 8 and
    ``docs/STATUS.md`` [G-8].

    Args:
        raw_items: List of raw items (dicts or already-typed objects)
        expected_type: The expected Pydantic model type
        builder: Function that converts a dict to the typed object
        label: Short caller-supplied tag used in the skip line
            (e.g. ``"attributes"``, ``"skills"``); keeps log/Job-warning
            output attributable to its caller.
        skipped: Optional accumulator list — items that fail to build are
            appended here as short strings (no exceptions leak). When
            ``None``, skip events are only logged.

    Returns:
        List of successfully built typed objects
    """
    result: list[T] = []
    for item in raw_items:
        if isinstance(item, expected_type):
            result.append(item)
            continue
        if not isinstance(item, dict):
            _record_skip(label, item, type(item).__name__, "not a dict", skipped)
            continue
        try:
            result.append(builder(item))
        except Exception as exc:
            _record_skip(label, item, type(item).__name__, type(exc).__name__, skipped)
            continue
    return result


def _record_skip(
    label: str,
    item: Any,
    item_type_name: str,
    error_class: str,
    skipped: list[str] | None,
) -> None:
    """Log a skip event and (optionally) record a short note in ``skipped``.

    The short note (max ~120 chars) is shaped to fit multiple lines in a
    single 400-char ``IngestionJobUpdate.warnings`` entry — see
    ``docs/architecture/GAP_REMEDIATION_PLAN.md`` G-8(a).
    """
    item_str = repr(item)[:60]
    note = f"{label or '?'}:{item_str}:{error_class}"[:120]
    if skipped is not None:
        skipped.append(note)
    logger.warning(
        "ingest._build_typed_list.skip",
        label=label,
        item=repr(item)[:200],
        error_class=error_class,
        item_type=item_type_name,
    )


def _build_attributes(
    charsheet_data: dict[str, Any],
    *,
    label: str = "attributes",
    skipped: list[str] | None = None,
) -> list[AttributeDefinition]:
    """Extract and validate attribute definitions from raw charsheet data."""

    def builder(a: dict[str, Any]) -> AttributeDefinition:
        return AttributeDefinition(
            name=a["name"][:100],
            abbreviation=a.get("abbreviation", a["name"][:10])[:10],
            min_value=int(a.get("min_value", 1)),
            max_value=int(a.get("max_value", 20)),
            default_value=int(a.get("default_value", 10)),
            modifier_formula=a.get("modifier_formula"),
        )

    return _build_typed_list(
        charsheet_data.get("attributes", []),
        AttributeDefinition,
        builder,
        label=label,
        skipped=skipped,
    )


def _build_skills(
    charsheet_data: dict[str, Any],
    *,
    label: str = "skills",
    skipped: list[str] | None = None,
) -> list[SkillDefinition]:
    """Extract and validate skill definitions from raw charsheet data."""

    def builder(s: dict[str, Any]) -> SkillDefinition:
        return SkillDefinition(
            name=s["name"][:100],
            abbreviation=s.get("abbreviation"),
            linked_attribute=s.get("linked_attribute"),
            description=s.get("description"),
        )

    return _build_typed_list(
        charsheet_data.get("skills", []),
        SkillDefinition,
        builder,
        label=label,
        skipped=skipped,
    )


def _build_resources(
    charsheet_data: dict[str, Any],
    *,
    label: str = "resources",
    skipped: list[str] | None = None,
) -> list[ResourceDefinition]:
    """Extract and validate resource definitions from raw charsheet data."""

    def builder(r: dict[str, Any]) -> ResourceDefinition:
        return ResourceDefinition(
            name=r["name"][:100],
            abbreviation=r.get("abbreviation", r["name"][:10])[:10],
            calculation=r.get("calculation"),
            min_value=int(r.get("min_value", 0)),
            recovers_on=r.get("recovers_on"),
            depleted_effect=r.get("depleted_effect"),
        )

    return _build_typed_list(
        charsheet_data.get("resources", []),
        ResourceDefinition,
        builder,
        label=label,
        skipped=skipped,
    )


def _build_conditions(
    charsheet_data: dict[str, Any],
    *,
    label: str = "conditions",
    skipped: list[str] | None = None,
) -> list[ConditionDefinition]:
    """Extract and validate condition definitions from raw charsheet data."""

    def builder(c: dict[str, Any]) -> ConditionDefinition:
        return ConditionDefinition(
            name=c["name"][:100],
            description=c.get("description"),
            roll_modifier=int(c["roll_modifier"]) if c.get("roll_modifier") is not None else None,
            roll_mode_override=c.get("roll_mode_override"),
        )

    return _build_typed_list(
        charsheet_data.get("conditions", []),
        ConditionDefinition,
        builder,
        label=label,
        skipped=skipped,
    )


def _build_scenery_rules(
    charsheet_data: dict[str, Any],
    *,
    label: str = "scenery_rules",
    skipped: list[str] | None = None,
) -> list[SceneryRule]:
    """Extract and validate scenery rules from raw charsheet data."""

    def builder(s: dict[str, Any]) -> SceneryRule:
        return SceneryRule(
            keyword=s["keyword"][:100],
            trigger_verbs=s.get("trigger_verbs", []),
            roll_modifier=int(s["roll_modifier"]) if s.get("roll_modifier") is not None else None,
            roll_mode_override=s.get("roll_mode_override"),
            reason_text=s.get("reason_text"),
        )

    return _build_typed_list(
        charsheet_data.get("scenery_rules", []),
        SceneryRule,
        builder,
        label=label,
        skipped=skipped,
    )


def _build_core_mechanic(charsheet_data: dict[str, Any]) -> CoreMechanic:
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
    typed_rules: list[GameRule],
    charsheet_data: dict[str, Any],
    system_name: str,
) -> list[GameRule]:
    """Merge power/subsystem entries from charsheet into typed rules (deduped)."""
    existing_rule_names = {rule.name.lower().strip() for rule in typed_rules}

    for power in charsheet_data.get("powers", []):
        name = str(power.get("name", "")).strip()
        if not name or name.lower() in existing_rule_names:
            continue
        category = str(power.get("category", "power")).strip() or "power"
        description = str(power.get("description", "")).strip() or f"{name} is a named {category} in {system_name}."
        # [G-8] Preserve provenance: the upstream extraction may carry
        # ``source_ref``/``formula`` on the power dict. Older versions
        # hardcoded both to ``None`` here, silently losing provenance.
        raw_source_ref = power.get("source_ref")
        raw_formula = power.get("formula")
        typed_rules.append(
            GameRule(
                name=name[:200],
                rule_type=GameRuleType.CUSTOM,
                description=f"{category.title()} option: {description}"[:2000],
                formula=raw_formula if isinstance(raw_formula, str) else None,
                source_ref=(raw_source_ref[:200] if isinstance(raw_source_ref, str) else None),
                tags=["subsystem", f"power:{category.lower().replace(' ', '_')}"],
            )
        )
        existing_rule_names.add(name.lower())

    for subsystem in charsheet_data.get("subsystems", []):
        name = str(subsystem.get("name", "")).strip()
        if not name or name.lower() in existing_rule_names:
            continue
        scope = str(subsystem.get("scope", "custom")).strip() or "custom"
        description = str(subsystem.get("description", "")).strip() or f"{name} is a named subsystem in {system_name}."
        # [G-8] Same provenance fix as powers (above).
        raw_source_ref = subsystem.get("source_ref")
        raw_formula = subsystem.get("formula")
        typed_rules.append(
            GameRule(
                name=name[:200],
                rule_type=GameRuleType.CUSTOM,
                description=f"Subsystem ({scope}): {description}"[:2000],
                formula=raw_formula if isinstance(raw_formula, str) else None,
                source_ref=(raw_source_ref[:200] if isinstance(raw_source_ref, str) else None),
                tags=["subsystem", f"scope:{scope.lower().replace(' ', '_')}"],
            )
        )
        existing_rule_names.add(name.lower())

    return typed_rules


# Keyword vocabulary used to cross-check a step's declared `step_type`
# against its own title/instructions text (INGESTION_PIPELINE_AUDIT.md
# Finding 2). CUSTOM is intentionally absent — it has no expected content,
# so it always passes. This mirrors (but doesn't import) the vocabulary in
# `character_creation_loop._FIELD_KEYS_BY_STEP` — that module drives the
# live conversational parser, this one validates ingestion/hand-authoring,
# and the two shouldn't be coupled by a cross-import across analyzer/loops.
_STEP_TYPE_KEYWORDS: dict[CreationStepType, tuple[Any, ...]] = {
    CreationStepType.CHOOSE_ARCHETYPE: ("archetype",),
    CreationStepType.CHOOSE_SPECIES: ("species", "race", "heritage", "ancestry"),
    CreationStepType.CHOOSE_CLASS: ("class", "clan", "archetype"),
    CreationStepType.GENERATE_STATS: ("stat", "ability score", "attribute", "dot"),
    CreationStepType.GENERATE_ATTRIBUTES: ("attribute", "dot", "stat"),
    CreationStepType.ASSIGN_STATS: ("stat", "attribute", "ability score", "dot"),
    CreationStepType.CHOOSE_BACKGROUND: ("background", "merit", "flaw"),
    CreationStepType.CHOOSE_POWERS: ("power", "spell", "discipline", "feat"),
    CreationStepType.CHOOSE_SKILLS: ("skill", "abilit", "proficienc"),
    CreationStepType.CHOOSE_EQUIPMENT: ("equipment", "gear", "loadout", "item"),
    CreationStepType.CALCULATE_DERIVED: (
        "derived",
        "calculat",
        "health",
        "willpower",
        "hit point",
    ),
    CreationStepType.WRITE_BACKSTORY: (
        "backstory",
        "history",
        "sire",
        "predator",
        "touchstone",
        "conviction",
    ),
    CreationStepType.CHOOSE_NAME: ("name",),
    CreationStepType.CHOOSE_ATTRIBUTES: ("attribute", "stat", "dot"),
    CreationStepType.CHOOSE_DISCIPLINES: ("discipline", "power"),
    CreationStepType.CHOOSE_ADVANTAGES: ("advantage", "merit", "flaw", "background"),
}


def _step_type_matches_content(step_type: CreationStepType, title: str, instructions: str) -> bool:
    """Does this step's own title/instructions text support its declared type?

    CUSTOM has no expected vocabulary and always matches. Any step_type not
    in the table (shouldn't happen given the enum is closed) also matches,
    to fail open rather than mislabel something we don't have a rule for.
    """
    keywords = _STEP_TYPE_KEYWORDS.get(step_type)
    if not keywords:
        return True
    haystack = f"{title} {instructions}".lower()
    return any(kw in haystack for kw in keywords)


def _build_character_creation(
    creation_procedure_data: dict[str, Any],
) -> CharacterCreationProcedure | None:
    """Build character creation procedure from extracted data."""
    if not creation_procedure_data.get("steps") and not creation_procedure_data.get("ability_score_generation"):
        return None

    # Build creation steps
    creation_steps: list[CreationStep] = []
    for s in creation_procedure_data.get("steps", []):
        if isinstance(s, CreationStep):
            # Hand-authored/passthrough steps get the same semantic check
            # as ingested ones (Finding 8: one validation path for both).
            if s.step_type != CreationStepType.CUSTOM and not _step_type_matches_content(
                s.step_type, s.title, s.instructions
            ):
                logger.warning(
                    "Creation step declared as '%s' but its title/instructions "
                    "don't mention any expected keyword — relabeling to CUSTOM "
                    "to avoid misrouted field extraction. title=%r",
                    s.step_type.value,
                    s.title,
                )
                s = s.model_copy(update={"step_type": CreationStepType.CUSTOM})
            creation_steps.append(s)
            continue
        try:
            step_type = CreationStepType(s.get("step_type", "custom"))
        except ValueError:
            step_type = CreationStepType.CUSTOM
        title = str(s.get("title", ""))[:200]
        instructions = str(s.get("instructions", ""))[:2000]
        if step_type != CreationStepType.CUSTOM and not _step_type_matches_content(step_type, title, instructions):
            logger.warning(
                "Creation step declared as '%s' but its title/instructions "
                "don't mention any expected keyword — relabeling to CUSTOM "
                "to avoid misrouted field extraction. title=%r",
                step_type.value,
                title,
            )
            step_type = CreationStepType.CUSTOM
        creation_steps.append(
            CreationStep(
                step_number=int(s.get("step_number", len(creation_steps) + 1)),
                step_type=step_type,
                title=title,
                instructions=instructions,
                is_optional=bool(s.get("is_optional", False)),
                options=[str(o)[:200] for o in s.get("options", [])],
            )
        )

    # Build creation logic
    creation_logic: list[CreationLogicStep] = []
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
    ability_score_gen: AbilityScoreGeneration | None = None
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
    creation_backgrounds: list[Background] = [
        Background(
            name=str(bg.get("name", ""))[:200],
            description=str(bg.get("description", ""))[:1000],
            skill_proficiencies=bg.get("skill_proficiencies", []),
            equipment=bg.get("equipment", []),
        )
        for bg in creation_procedure_data.get("backgrounds", [])
    ]

    # Build starting packages
    creation_packages: list[StartingPackage] = [
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
    advancement: AdvancementSystem | None = None
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


def _build_npc_stat_blocks(npc_data: dict[str, Any]) -> list[NPCStatBlock]:
    """Build NPC stat blocks from raw extraction data."""
    npc_stat_blocks: list[NPCStatBlock] = []
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


def _build_npc_creation_rules(npc_data: dict[str, Any]) -> NPCCreationRules | None:
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


def _build_resolution_mechanics(
    raw_mechanics: list[dict[str, Any]],
    *,
    label: str = "resolution_mechanics",
    skipped: list[str] | None = None,
) -> list[ResolutionMechanic]:
    """Extract and validate detailed resolution mechanics from raw extraction data."""

    def builder(rm: dict[str, Any]) -> ResolutionMechanic:
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
            difficulty_model=str(rm.get("difficulty_model", "fixed_dc"))[:200],
            difficulty_range=rm.get("difficulty_range"),
            success_degrees=degrees,
            success_type=s_type,
            critical_success=rm.get("critical_success"),
            critical_failure=rm.get("critical_failure"),
            consequence_on_failure=rm.get("consequence_on_failure"),
            complication_mechanic=rm.get("complication_mechanic"),
        )

    return _build_typed_list(
        raw_mechanics,
        ResolutionMechanic,
        builder,
        label=label,
        skipped=skipped,
    )


def _detect_degenerate_extraction(
    charsheet_data: dict[str, Any],
    attributes: list[AttributeDefinition],
    skills: list[SkillDefinition],
    resources: list[ResourceDefinition],
    character_creation: CharacterCreationProcedure | None,
) -> str | None:
    """Return a human-readable reason if this extraction looks degenerate.

    INGESTION_PIPELINE_AUDIT.md Finding 5: a document with a placeholder
    ``core_mechanic`` (LLM returned nothing, so we fell back to
    d20/meet_or_beat defaults) or with literally zero populated fields
    across attributes/skills/resources/character_creation is
    indistinguishable, at rest, from a genuinely successful extraction —
    unless something checks for it and says so. Returns ``None`` when the
    extraction looks legitimate (partial misses across a large book are
    normal and NOT degenerate; this only catches *total* misses).
    """
    reasons: list[str] = []

    if not charsheet_data.get("core_mechanic"):
        reasons.append(
            "core_mechanic extraction returned nothing; "
            "type/formula/success_type are placeholder defaults, not real data"
        )

    if not any([attributes, skills, resources, character_creation]):
        reasons.append(
            "zero populated fields across attributes/skills/resources/"
            "character_creation — extraction likely failed entirely"
        )

    if not reasons:
        return None
    return "; ".join(reasons)


async def save_game_system(
    system_name: str,
    game_rules: list[dict[str, Any]],
    source_name: str,
    charsheet_data: dict[str, Any] | None = None,
    creation_procedure_data: dict[str, Any] | None = None,
    npc_data: dict[str, Any] | None = None,
    random_tables: list[ExtractedRandomTable] | None = None,
    agendas: list[ExtractedAgenda] | None = None,
    topologies: list[ExtractedTopology] | None = None,
    character_profiles: list[ExtractedCharacterProfile] | None = None,
    generation_templates: list[ExtractedGenerationTemplate] | None = None,
    resolution_mechanics: list[dict[str, Any]] | None = None,
    source_document_id: UUID | None = None,
    job_id: UUID | None = None,
) -> tuple[UUID | None, EmbeddedGameSystem]:
    """
    Save extracted game system to MongoDB and return (id, EmbeddedGameSystem).

    Returns a 2-tuple so the caller can store the embedded copy on the
    KnowledgePack AND keep the reference ID for the ``game_systems``
    collection.

    [G-8] When ``job_id`` is supplied and any ``_build_typed_list``
    skip events were recorded, a one-line summary (≤400 chars to fit
    ``IngestionJobUpdate.warnings``'s cap) is appended to the job's
    warnings list via ``mongodb_update_ingestion_job``. See
    ``docs/architecture/GAP_REMEDIATION_PLAN.md`` G-8(a).
    """
    from monitor_agents.utils.analyzer_support import (
        filter_player_attributes,
        filter_player_resources,
        filter_player_skills,
    )

    charsheet_data = charsheet_data or {}
    creation_procedure_data = creation_procedure_data or {}
    npc_data = npc_data or {}

    # [G-8] Skip accumulator shared by all ``_build_typed_list`` callers in
    # this run. Reset per-call to scope events to this save_game_system.
    skipped: list[str] = []

    # Build typed components (all six thread through ``skipped``)
    typed_rules = _build_typed_rules(game_rules)
    attributes = _build_attributes(charsheet_data, skipped=skipped)
    skills = _build_skills(charsheet_data, skipped=skipped)
    resources = _build_resources(charsheet_data, skipped=skipped)
    conditions = _build_conditions(charsheet_data, skipped=skipped)
    scenery_rules = _build_scenery_rules(charsheet_data, skipped=skipped)
    resolution_mechanics_list = _build_resolution_mechanics(resolution_mechanics or [], skipped=skipped)

    # Apply post-extraction filters
    attributes = filter_player_attributes(attributes)
    skills = filter_player_skills(skills)
    resources = filter_player_resources(resources)

    # Merge powers/subsystems into rules
    typed_rules = _merge_powers_and_subsystems(typed_rules, charsheet_data, system_name)

    # Build core mechanic
    core_mechanic = _build_core_mechanic(charsheet_data)

    # Build character creation procedure
    character_creation = _build_character_creation(creation_procedure_data)

    # Build NPC components
    npc_stat_blocks = _build_npc_stat_blocks(npc_data)
    npc_creation_rules = _build_npc_creation_rules(npc_data)

    # Build and persist random tables
    table_ids = _build_random_tables(random_tables or [])

    # Detect a degenerate extraction BEFORE persisting — loud, not silent
    # (INGESTION_PIPELINE_AUDIT.md Finding 5).
    degenerate_reason = _detect_degenerate_extraction(charsheet_data, attributes, skills, resources, character_creation)
    needs_review = degenerate_reason is not None
    if needs_review:
        logger.warning(
            "Degenerate game system extraction for '%s' from '%s': %s",
            system_name,
            source_name,
            degenerate_reason,
        )

    # [G-8] Surface items silently dropped by _build_typed_list during this
    # run. Older versions logged nothing — the count was invisible to
    # operators. Two surfaces now: a WARNING log (always), and one
    # ≤400-char summary appended to ``job_id``'s ``IngestionJob.warnings``
    # when the caller supplies ``job_id``.
    if skipped:
        logger.warning(
            "save_game_system.complete_with_skipped_items",
            system_name=system_name,
            source_name=source_name,
            skipped_count=len(skipped),
            sample=skipped[:3],
        )
        if job_id is not None:
            try:
                from monitor_data.schemas.ingestion_jobs import (
                    IngestionJobUpdate,
                )
                from monitor_data.tools.mongodb_tools.ingestion_jobs import (
                    mongodb_update_ingestion_job,
                )

                summary = (
                    f"persistence skipped {len(skipped)} item(s) for "
                    f"system='{system_name}' from '{source_name}': "
                    f"{'; '.join(skipped[:5])}"
                )[:400]
                mongodb_update_ingestion_job(job_id, IngestionJobUpdate(warnings=[summary]))
            except Exception as exc:
                logger.warning(
                    "save_game_system.job_warning_append_failed",
                    job_id=str(job_id),
                    error=str(exc)[:200],
                )

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
        needs_review=needs_review,
        degenerate_reason=degenerate_reason,
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
                needs_review=needs_review,
                degenerate_reason=degenerate_reason,
            )
        )
        return system.id, embedded
    except Exception as exc:
        logger.warning("Failed to save game system '%s': %s", system_name, exc)
        # Still return the embedded data even if the separate collection
        # write failed — the pack itself carries the system regardless.
        return None, embedded
