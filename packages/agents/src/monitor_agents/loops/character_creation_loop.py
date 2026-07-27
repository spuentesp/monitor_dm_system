"""
Character Creation Loop — Conversational, schema-driven character builder.

LAYER: 2 (agents)
IMPORTS FROM: monitor_data (Layer 1), langgraph, external libs
CALLED BY: story_loop.py or conversation_loop.py

Uses GameSystemRuntime to drive a step-by-step character creation
conversation. The system reads the character_creation procedure from
the game system schema and guides the player through each step.

Flow:
  load_system → present_step → await_player → process_input → (loop or finish)

No game-specific names are hardcoded — everything comes from the schema.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from langgraph.graph import END, StateGraph
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# =============================================================================
# STATE SCHEMA
# =============================================================================


class CharacterCreationState(BaseModel):
    """State flowing through each node of the creation loop."""

    # Session context
    scene_id: UUID | None = None
    story_id: UUID | None = None
    universe_id: UUID | None = None

    # Game system context (raw MongoDB document)
    game_context: dict[str, Any] = Field(default_factory=dict)

    # Creation state
    current_step_index: int = 0
    total_steps: int = 0
    creation_steps: list[dict[str, Any]] = Field(default_factory=list)

    # Accumulated character data
    character_data: dict[str, Any] = Field(default_factory=dict)
    attributes: dict[str, int] = Field(default_factory=dict)
    skills: dict[str, Any] = Field(default_factory=dict)
    resources: dict[str, Any] = Field(default_factory=dict)
    choices: dict[str, Any] = Field(default_factory=dict)
    background: str | None = None
    character_name: str | None = None
    concept: str | None = None

    # Conversation
    gm_message: str | None = None
    player_input: str | None = None
    step_prompt: str | None = None

    # Flow control
    creation_complete: bool = False
    awaiting_input: bool = False
    error: str | None = None


# =============================================================================
# NODES
# =============================================================================


def load_system(state: CharacterCreationState) -> dict[str, Any]:
    """Load game system and extract creation procedure steps."""
    if not state.game_context:
        return {
            "error": "No game system loaded. Cannot start character creation.",
            "creation_complete": True,
        }

    try:
        from monitor_agents.game_system import GameSystemRuntime

        gsr = GameSystemRuntime(state.game_context)

        # Get creation procedure from the schema
        char_creation = gsr._char_creation or {}
        steps_raw = char_creation.get("steps") or []

        # If no steps defined, build a generic flow from the schema
        if not steps_raw:
            steps_raw = _infer_creation_steps(gsr)

        # Ensure a name step exists (inject at start if missing). Use a valid
        # ``step_number`` (≥1) and the canonical enum value so the step
        # survives the CreationStepType schema check in
        # data-layer/schemas/game_systems.py.
        has_name_step = any(
            s.get("step_type") in ("choose_name", "name") or s.get("type") in ("choose_name", "name") for s in steps_raw
        )
        if not has_name_step:
            steps_raw.insert(
                0,
                {
                    "step_number": 1,
                    "step_type": "choose_name",
                    "title": "Character Name",
                    "instructions": "What is your character's name?",
                    "is_optional": False,
                    "options": [],
                },
            )

        # Store system info for reference
        system_name = gsr._doc.get("name", "Unknown System")
        attrs = gsr._primary_attributes
        tracks = gsr.get_tracks()

        # Initialize attributes with defaults
        initial_attrs = {}
        for attr in attrs:
            abbr = (attr.get("abbreviation") or attr.get("name", "?")[:3]).upper()
            default = attr.get("default_value")
            if default is None:
                min_v = attr.get("min_value", 0)
                max_v = attr.get("max_value", 20)
                default = (min_v + max_v) // 2
            initial_attrs[abbr] = default

        # Build initial track state
        track_state = {}
        for track in tracks:
            t_name = track.get("name", "")
            t_max = track.get("max_value") or track.get("min_value", 0)
            t_type = track.get("track_type", "resource")
            if t_type in ("resource", "stress", "advancement"):
                track_state[t_name] = {"current": t_max, "max": t_max}
            else:
                track_state[t_name] = {"current": track.get("min_value", 0), "max": t_max}

        return {
            "creation_steps": steps_raw,
            "total_steps": len(steps_raw),
            "current_step_index": 0,
            "attributes": initial_attrs,
            "resources": track_state,
            "character_data": {
                "system_name": system_name,
                "system_id": str(state.game_context.get("_id", "")),
            },
        }

    except Exception as exc:
        logger.error("Failed to load game system for character creation: %s", exc)
        return {
            "error": f"Failed to load game system: {exc}",
            "creation_complete": True,
        }


def present_step(state: CharacterCreationState) -> dict[str, Any]:
    """Generate a conversational prompt for the current creation step."""
    if state.creation_complete:
        return {"awaiting_input": False}

    steps = state.creation_steps
    idx = state.current_step_index

    if idx >= len(steps):
        # All steps done — finalize
        return {
            "creation_complete": True,
            "gm_message": _build_completion_message(state),
            "awaiting_input": False,
        }

    step = steps[idx]
    step_type = step.get("step_type") or step.get("type", "custom")
    title = step.get("title", f"Step {idx + 1}")
    instructions = step.get("instructions", "")
    options = step.get("options", [])
    optional = step.get("is_optional") if "is_optional" in step else step.get("optional", False)

    # Build contextual prompt
    current_attrs = _format_current_attrs(state)

    prompt_parts = [
        f"**{title}**",
        "",
    ]

    if instructions:
        prompt_parts.append(instructions)

    if options:
        prompt_parts.append("")
        prompt_parts.append("Options: " + ", ".join(str(o) for o in options))

    if current_attrs and idx > 0:
        prompt_parts.append("")
        prompt_parts.append(f"_Current attributes: {current_attrs}_")

    if optional:
        prompt_parts.append("")
        prompt_parts.append("*(This step is optional — type 'skip' to skip)*")

    step_prompt = "\n".join(prompt_parts)

    # If this step has a fixed resolution (e.g. calculate derived stats), do it automatically
    if step_type == "calculate_derived":
        return _auto_calculate_derived(state, step)

    return {
        "step_prompt": step_prompt,
        "gm_message": step_prompt,
        "awaiting_input": True,
    }


# Mapping of step_type → list of expected field names for multi-line
# answer parsing. When the LLM dumps the whole character sheet per step,
# each parser picks out the field relevant to itself. System-agnostic.
_FIELD_KEYS_BY_STEP: dict[str, tuple] = {
    "choose_name": ("name", "character name"),
    "choose_concept": ("concept",),
    "choose_class": ("class", "clan", "archetype"),
    "choose_species": ("species", "heritage", "ancestry"),
    "choose_disciplines": ("discipline", "disciplines", "powers"),
    "choose_background": ("background", "backgrounds"),
    "choose_equipment": ("equipment", "gear", "loadout"),
    "choose_feats": ("feat", "feats"),
    "choose_spells": ("spell", "spells"),
    "write_backstory": ("backstory", "sire", "predator", "history"),
    # These two were the actual root cause of INGESTION_PIPELINE_AUDIT.md
    # Finding 1: without an entry here, the isolation step was skipped and
    # the parser received the player's *entire* multi-field answer dump
    # instead of just the "Dot Assignments:"/"Skill Picks:" line.
    "generate_attributes": ("dot assignments", "dots", "attributes", "stats"),
    "assign_attributes": ("dot assignments", "dots", "attributes", "stats"),
    "choose_skills": ("skill picks", "skills", "skill"),
}


def _extract_field(text: str, *expected_keys: str) -> str | None:
    """Parse "Key: Value" lines, return the value for the first matching key.

    Designed for LLM outputs that dump the full character sheet per step.
    Lookup is case-insensitive and matches the key in any position (with or
    without surrounding whitespace).
    """
    lowered = tuple(k.lower() for k in expected_keys)
    for raw in text.splitlines():
        line = raw.strip()
        if not line or ":" not in line:
            continue
        key, _, value = line.partition(":")
        if key.strip().lower() in lowered:
            return value.strip() or None
    return None


async def process_input(state: CharacterCreationState) -> dict[str, Any]:
    """Process player input for the current step and advance."""
    if not state.player_input:
        return {"awaiting_input": True}

    player_text = state.player_input.strip()
    idx = state.current_step_index

    if idx >= len(state.creation_steps):
        return {"creation_complete": True}

    step = state.creation_steps[idx]
    step_type = step.get("step_type") or step.get("type", "custom")
    step_title = step.get("title", f"Step {idx + 1}")
    optional = step.get("is_optional") if "is_optional" in step else step.get("optional", False)

    # Handle skip for optional steps
    if optional and player_text.lower() in ("skip", "pass", "next"):
        return {
            "current_step_index": idx + 1,
            "player_input": None,
            "choices": {**state.choices, step.get("title", f"step_{idx}"): "skipped"},
        }

    # --- Multi-line answer parsing ---
    # When the player LLM dumps the full character sheet per step
    # (e.g. "Name: Kael\nClan: Ventrue\nClass: ...\n..."), the step
    # parser only wants the line keyed for this step. System-agnostic:
    # the helper just looks for the first "Key: Value" line whose key
    # is the expected field for this step_type, regardless of system.
    keys_for_step = _FIELD_KEYS_BY_STEP.get(step_type)
    if keys_for_step:
        extracted = _extract_field(player_text, *keys_for_step)
        if extracted:
            player_text = extracted

    updates: dict[str, Any] = {"player_input": None}

    try:
        if step_type == "choose_name":
            updates["character_name"] = player_text
            updates["character_data"] = {**state.character_data, "name": player_text}

        elif step_type == "choose_concept":
            updates["concept"] = player_text
            updates["character_data"] = {**state.character_data, "concept": player_text}

        elif step_type in ("generate_attributes", "assign_attributes"):
            new_attrs, new_resources = await _extract_attribute_and_resource_assignments(
                player_text, state.attributes, state.resources, state.game_context
            )
            updates["attributes"] = new_attrs
            updates["resources"] = new_resources

        elif step_type == "choose_class":
            choice = await _match_option(player_text, step.get("options", []), step_title)
            # If "class" already taken (e.g. Vampire has clan + disciplines both as choose_class),
            # use the step title as key to avoid overwriting.
            choice_key = "class" if "class" not in state.choices else step.get("title", f"class_{idx}")
            updates["choices"] = {**state.choices, choice_key: choice or player_text}
            updates["character_data"] = {**state.character_data, choice_key: choice or player_text}

        elif step_type == "choose_species":
            choice = await _match_option(player_text, step.get("options", []), step_title)
            updates["choices"] = {**state.choices, "species": choice or player_text}
            updates["character_data"] = {**state.character_data, "species": choice or player_text}

        elif step_type in ("choose_background", "choose_disciplines", "choose_advantages"):
            choice = await _match_option(player_text, step.get("options", []), step_title)
            mapped_key = step.get("title", step_type.replace("choose_", "")).lower().replace(" ", "_")
            updates["background"] = choice or player_text
            updates["choices"] = {**state.choices, mapped_key: choice or player_text}
            updates["character_data"] = {**state.character_data, mapped_key: choice or player_text}

        elif step_type == "choose_skills":
            skill_choices = await _parse_skill_choices(player_text, state.game_context)
            updates["skills"] = {**state.skills, **skill_choices}

        elif step_type == "choose_equipment":
            updates["choices"] = {**state.choices, "equipment": player_text}
            updates["character_data"] = {**state.character_data, "equipment": player_text}

        elif step_type == "choose_feats":
            choice = await _match_option(player_text, step.get("options", []), step_title)
            updates["choices"] = {**state.choices, "feats": choice or player_text}
            updates["character_data"] = {**state.character_data, "feats": choice or player_text}

        elif step_type == "choose_spells":
            updates["choices"] = {**state.choices, "spells": player_text}
            updates["character_data"] = {**state.character_data, "spells": player_text}

        elif step_type == "write_backstory":
            updates["choices"] = {**state.choices, "backstory": player_text}
            updates["character_data"] = {**state.character_data, "backstory": player_text}

        else:
            # Generic custom step (e.g. perk selection, which has no
            # dedicated step_type in most ingested schemas). When the
            # schema supplies options for this step, match against them
            # the same way named steps do -- store the validated choice,
            # not raw unvalidated text.
            options = step.get("options") or []
            choice = await _match_option(player_text, options, step_title) if options else None
            updates["choices"] = {**state.choices, step_title: choice or player_text}
            updates["character_data"] = {**state.character_data, step_title: choice or player_text}

        # Advance to next step
        updates["current_step_index"] = idx + 1

    except Exception as exc:
        logger.warning("Error processing creation input for step %d: %s", idx, exc)
        updates["error"] = f"Could not process that input. Try again? ({exc})"

    return updates


# =============================================================================
# GRAPH BUILDER
# =============================================================================


def build_character_creation_graph() -> StateGraph:
    """Build the LangGraph StateGraph for character creation."""
    graph = StateGraph(CharacterCreationState)

    graph.add_node("load_system", load_system)
    graph.add_node("present_step", present_step)
    graph.add_node("process_input", process_input)

    graph.set_entry_point("load_system")
    graph.add_edge("load_system", "present_step")

    graph.add_conditional_edges(
        "present_step",
        _route_after_present,
        {
            "await": "process_input",
            "auto": "present_step",  # auto-advance for calculated steps
            "done": END,
        },
    )
    graph.add_conditional_edges(
        "process_input",
        _route_after_process,
        {
            "continue": "present_step",
            "retry": "present_step",
            "done": END,
        },
    )

    return graph


def _route_after_present(state: CharacterCreationState) -> str:
    """Route after presenting a step."""
    if state.creation_complete:
        return "done"
    if state.awaiting_input:
        return "await"
    # Auto-advance (e.g. calculate_derived)
    return "auto"


def _route_after_process(state: CharacterCreationState) -> str:
    """Route after processing input."""
    if state.error:
        return "retry"
    if state.creation_complete or state.current_step_index >= state.total_steps:
        return "done"
    return "continue"


# =============================================================================
# LOOP CLASS
# =============================================================================


class CharacterCreationLoop:
    """
    High-level interface for the character creation loop.

    Usage:
        loop = CharacterCreationLoop(game_context=gs_doc)
        result = await loop.run()
    """

    def __init__(
        self,
        game_context: dict[str, Any],
        scene_id: UUID | None = None,
        story_id: UUID | None = None,
    ) -> None:
        self._game_context = game_context
        self._scene_id = scene_id
        self._story_id = story_id
        self._graph = build_character_creation_graph()
        self._state = CharacterCreationState(
            scene_id=scene_id,
            story_id=story_id,
            game_context=game_context,
        )

    async def start(self) -> dict[str, Any]:
        """Initialize the loop and return the first GM prompt."""
        result = load_system(self._state)
        self._state = self._state.model_copy(update=result)

        if self._state.creation_complete:
            return {
                "complete": True,
                "error": self._state.error,
                "character": self._build_final_character(),
            }

        step_result = present_step(self._state)
        self._state = self._state.model_copy(update=step_result)

        return {
            "complete": False,
            "gm_message": self._state.gm_message,
            "step_index": self._state.current_step_index,
            "total_steps": self._state.total_steps,
            "step_prompt": self._state.step_prompt,
        }

    async def process_player_input(self, player_input: str) -> dict[str, Any]:
        """Process player input and advance to next step."""
        self._state = self._state.model_copy(update={"player_input": player_input})

        result = await process_input(self._state)
        self._state = self._state.model_copy(update=result)

        if self._state.current_step_index >= self._state.total_steps:
            self._state = self._state.model_copy(update={"creation_complete": True})
            return {
                "complete": True,
                "gm_message": _build_completion_message(self._state),
                "character": self._build_final_character(),
            }

        step_result = present_step(self._state)
        self._state = self._state.model_copy(update=step_result)

        return {
            "complete": self._state.creation_complete,
            "gm_message": self._state.gm_message,
            "step_index": self._state.current_step_index,
            "total_steps": self._state.total_steps,
            "error": self._state.error,
        }

    def _build_final_character(self) -> dict[str, Any]:
        """Build the final character sheet from accumulated state."""
        base = {
            "name": self._state.character_name,
            "concept": self._state.concept,
            "system_name": self._state.character_data.get("system_name"),
            "attributes": self._state.attributes,
            "skills": self._state.skills,
            "resources": self._state.resources,
            "choices": self._state.choices,
            "background": self._state.background,
        }
        try:
            from monitor_agents.game_system import GameSystemRuntime

            gsr = GameSystemRuntime(self._game_context)
            # format_character_sheet expects {stats: {STR: val, ...}, derived: {HP: val}, rolls_detail: {}}
            rolled = {
                "stats": self._state.attributes,
                "derived": {
                    name: val.get("current", val) if isinstance(val, dict) else val
                    for name, val in self._state.resources.items()
                },
                "rolls_detail": {},
            }
            sheet = gsr.format_character_sheet(rolled)
            base["sheet_markdown"] = sheet
        except Exception as exc:
            logger.warning("Could not format final sheet: %s", exc)
        return base


# =============================================================================
# HELPERS
# =============================================================================


def _infer_creation_steps(gsr: Any) -> list[dict[str, Any]]:
    """Infer creation steps from the game system schema when no explicit steps exist."""
    steps = []
    attrs = gsr._primary_attributes
    tracks = gsr.get_tracks()
    char_creation = gsr._char_creation or {}

    # Step 1: Character concept/name
    steps.append(
        {
            "type": "choose_name",
            "title": "Character Name",
            "instructions": "What is your character's name?",
            "optional": False,
        }
    )

    # Step 2: Concept/background if available
    if char_creation.get("backgrounds"):
        bg_options = [b.get("name", str(b)) for b in char_creation["backgrounds"]]
        steps.append(
            {
                "type": "choose_background",
                "title": "Background",
                "instructions": "Choose your character's background.",
                "options": bg_options,
                "optional": False,
            }
        )

    # Step 3: Class/archetype if defined
    tiered = gsr.get_tiered_systems()
    if tiered:
        for ts in tiered:
            ts_type = ts.get("type", "")
            if ts_type in ("class", "archetype", "clan", "origin"):
                tiers = gsr.get_available_tiers(ts.get("name", ""))
                options = [t.get("name", str(t)) for t in (tiers or [])]
                steps.append(
                    {
                        "type": "choose_class",
                        "title": f"Choose {ts.get('name', 'Class')}",
                        "instructions": f"Select your character's {ts.get('name', 'class')}.",
                        "options": options,
                        "optional": False,
                    }
                )
                break  # Only one primary class selection

    # Step 4: Attributes
    if attrs:
        attr_names = [a.get("name", a.get("abbreviation", "?")) for a in attrs]
        steps.append(
            {
                "type": "generate_attributes",
                "title": "Assign Attributes",
                "instructions": (
                    f"Assign values to your attributes: {', '.join(attr_names)}. "
                    "Format: name=value (e.g. STR=16 DEX=14 CON=12)"
                ),
                "optional": False,
            }
        )

    # Step 5: Skills if defined
    skills = gsr._skills or []
    if skills:
        skill_names = [s.get("name", str(s)) for s in skills[:10]]
        steps.append(
            {
                "type": "choose_skills",
                "title": "Choose Skills",
                "instructions": (
                    f"Select your skills. Available: {', '.join(skill_names)}" + ("..." if len(skills) > 10 else "")
                ),
                "optional": False,
            }
        )

    # Step 6: Calculate derived stats
    if tracks or attrs:
        steps.append(
            {
                "type": "calculate_derived",
                "title": "Calculate Derived Stats",
                "instructions": "Computing derived statistics from your choices...",
                "optional": False,
            }
        )

    return steps


def _auto_calculate_derived(state: CharacterCreationState, step: dict[str, Any]) -> dict[str, Any]:
    """Auto-calculate derived stats and advance to next step."""
    try:
        from monitor_agents.game_system import GameSystemRuntime

        gsr = GameSystemRuntime(state.game_context)
        track_state = gsr.build_initial_track_state(stats=state.attributes)

        new_resources = {}
        for t_name, val in track_state.get("tracks", {}).items():
            t_max = track_state.get("track_maxes", {}).get(t_name, val)
            new_resources[t_name] = {"current": val, "max": t_max}

        return {
            "resources": {**state.resources, **new_resources},
            "current_step_index": state.current_step_index + 1,
            "awaiting_input": False,
        }
    except Exception as exc:
        logger.warning("Auto-calculate derived failed: %s", exc)
        return {
            "current_step_index": state.current_step_index + 1,
            "awaiting_input": False,
        }


def _safe_json_object(raw: str) -> dict[str, Any]:
    """Parse an LLM-emitted JSON object string, fail-soft to {} on any error."""
    import json

    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


async def _extract_attribute_and_resource_assignments(
    text: str,
    current_attributes: dict[str, int],
    current_resources: dict[str, Any],
    game_context: dict[str, Any],
) -> tuple[dict[str, int], dict[str, int]]:
    """Extract attribute and resource assignments from the player's
    free-text answer via LLM structured extraction (schema-driven: the
    system's own attribute/resource names, never hardcoded categories or
    phrasing patterns -- see the `no-brittle-patches` project rule this
    replaces regex parsing under).

    "roll"/"random" is a fixed player command, not free text needing
    interpretation -- handled directly, no LLM round-trip.

    Returns (updated_attributes, updated_resources). Never crashes, never
    loses existing values: any extraction failure returns the inputs
    unchanged.
    """
    attributes = dict(current_attributes)
    resources = dict(current_resources)
    stripped = text.strip().lower()

    if stripped in ("roll", "random", "roll stats", "surprise me"):
        try:
            from monitor_agents.game_system import GameSystemRuntime

            gsr = GameSystemRuntime(game_context)
            candidate = gsr.roll_character()
            if candidate and "attributes" in candidate:
                for k, v in candidate["attributes"].items():
                    if k.upper() in attributes:
                        attributes[k.upper()] = v
        except Exception:
            logger.debug("Random attribute roll failed", exc_info=True)
        return attributes, resources

    if not text.strip():
        return attributes, resources

    attr_defs = game_context.get("attributes") or []
    available_attributes = [
        {
            "name": a.get("name"),
            "abbreviation": (a.get("abbreviation") or str(a.get("name", ""))[:3]).upper(),
            "current_value": attributes.get((a.get("abbreviation") or str(a.get("name", ""))[:3]).upper(), 0),
            "min_value": a.get("min_value"),
            "max_value": a.get("max_value"),
        }
        for a in attr_defs
        if a.get("name")
    ]
    resource_names = {str(r.get("name", "")).strip() for r in (game_context.get("resources") or []) if r.get("name")}
    resource_names |= {str(t.get("name", "")).strip() for t in (game_context.get("tracks") or []) if t.get("name")}
    resource_names.discard("")
    available_resources = [{"name": name, "current_value": resources.get(name, 0)} for name in resource_names]

    try:
        import json

        from monitor_agents.character_creator.character_creation import AttributeAssignmentModule

        module = AttributeAssignmentModule()
        prediction = module(
            player_answer=text,
            available_attributes=json.dumps(available_attributes, default=str),
            available_resources=json.dumps(available_resources, default=str),
        )
        attr_updates = _safe_json_object(getattr(prediction, "attribute_assignments", "{}"))
        resource_updates = _safe_json_object(getattr(prediction, "resource_assignments", "{}"))
    except Exception as exc:
        logger.warning("Attribute/resource LLM extraction failed: %s", exc)
        return attributes, resources

    for key, value in attr_updates.items():
        key_upper = str(key).upper()
        if key_upper in attributes:
            try:
                attributes[key_upper] = int(value)
            except (TypeError, ValueError):
                continue

    for name, value in resource_updates.items():
        if name in resource_names:
            try:
                resources[name] = {"current": int(value), "max": int(value)}
            except (TypeError, ValueError):
                continue

    if not attr_updates and not resource_updates:
        logger.warning("Attribute/resource extraction had no effect: answer=%r", text[:200])

    return attributes, resources


async def _parse_skill_choices(text: str, game_context: dict[str, Any]) -> dict[str, Any]:
    """Extract skill selections (with optional ranks) from the player's
    free-text answer via LLM structured extraction, grounded in the game
    system's own skill list (schema-driven, no fixed tokenizing rules).

    The multi-line "LLM dumped the whole sheet" case is already isolated
    to this step's relevant text by `process_input`'s `_extract_field`
    call before this function ever runs, so no metadata-line stripping is
    needed here.
    """
    if not text or not text.strip():
        return {}

    skill_defs = game_context.get("skills") or []
    available_skills = [str(s.get("name", "")).strip() for s in skill_defs if s.get("name")]
    if not available_skills:
        return {}

    try:
        import json

        from monitor_agents.character_creator.character_creation import SkillSelectionModule

        module = SkillSelectionModule()
        prediction = module(
            player_answer=text,
            available_skills=json.dumps(available_skills, default=str),
        )
        selections = _safe_json_object(getattr(prediction, "skill_selections", "{}"))
    except Exception as exc:
        logger.warning("Skill selection LLM extraction failed: %s", exc)
        return {}

    valid_names = set(available_skills)
    skills = {name: value for name, value in selections.items() if name in valid_names}
    if not skills:
        logger.warning("Skill choice extraction had no effect: answer=%r", text[:200])
    return skills


async def _match_option(text: str, options: list[Any], step_title: str = "") -> str | None:
    """Match the player's free-text answer to one option via LLM
    extraction, grounded in the step's own option list (schema-driven --
    replaces plain substring matching, which required near-verbatim
    quoting and couldn't handle paraphrasing or full sentences)."""
    if not text or not text.strip() or not options:
        return None

    try:
        import json

        from monitor_agents.character_creator.text_matching import OptionMatchModule

        module = OptionMatchModule()
        prediction = module(
            player_answer=text,
            choice_context=step_title,
            available_options=json.dumps([str(o) for o in options], default=str),
        )
        matched = str(getattr(prediction, "matched_option", "") or "").strip()
    except Exception as exc:
        logger.warning("Option match LLM extraction failed: %s", exc)
        return None

    option_strs = {str(o): str(o) for o in options}
    if matched in option_strs:
        return option_strs[matched]
    # Tolerate the LLM returning the option verbatim but case-shifted.
    lowered = {str(o).lower(): str(o) for o in options}
    return lowered.get(matched.lower())


def _format_current_attrs(state: CharacterCreationState) -> str:
    """Format current attributes for display."""
    parts = []
    for k, v in state.attributes.items():
        parts.append(f"{k}={v}")
    return ", ".join(parts) if parts else ""


def _build_completion_message(state: CharacterCreationState) -> str:
    """Build the final completion message with character summary."""
    name = state.character_name or "Unnamed"
    parts = [
        "**Character Creation Complete!**",
        "",
        f"Name: **{name}**",
    ]

    if state.concept:
        parts.append(f"Concept: {state.concept}")
    if state.background:
        parts.append(f"Background: {state.background}")

    # Class/archetype from choices
    char_class = state.choices.get("class")
    if char_class:
        parts.append(f"Class: {char_class}")

    species = state.choices.get("species")
    if species:
        parts.append(f"Species: {species}")

    # Attributes
    if state.attributes:
        parts.append("")
        parts.append("**Attributes:** " + _format_current_attrs(state))

    # Resources
    if state.resources:
        parts.append("")
        parts.append("**Resources:**")
        for rname, rval in state.resources.items():
            if isinstance(rval, dict):
                parts.append(f"  - {rname}: {rval.get('current', '?')}/{rval.get('max', '?')}")
            else:
                parts.append(f"  - {rname}: {rval}")

    parts.append("")
    parts.append("_Your character is ready. The story awaits._")

    return "\n".join(parts)
