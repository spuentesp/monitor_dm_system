"""
Cast — who is who in the current scene.

LAYER: 2 (agents)
IMPORTS FROM: pydantic, structlog, typing, uuid (no data-layer, no loops)

The Cast answers, on every turn, the question the GM must never guess at:
which characters does the user control, which one is speaking right now,
which persona (the user's cross-world identity) stands behind each
incarnation, and which characters belong to the GM.

Built once per turn (see ``build_cast``), it is passed into SceneLoop node
state, GMAgent, Narrator and the memory extractor so that:

- the agency rule (never act/speak/think/feel for a user-controlled
  character) can be stated against a concrete roster (Task 2), and
- memories and facts written in play can carry ``witnesses`` — the cast
  members actually present (Task 8).

Transport: the cast is assembled in the UI layer (``get_scene_loop``, which
owns the session's controlled ids) and carried on ``SceneState.cast``, so the
scene-loop nodes read the same roster the session holds. A backend restart
between two turns changes nothing: the roster is rebuilt from the session on
every turn.
"""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

import structlog
from pydantic import BaseModel, Field, ValidationError

log = structlog.get_logger()

# The agency rule, placed next to every cast input and in the narrator / GM
# output fields (mirrors the G-4 hallucination-guard placement).
AGENCY_RULE = (
    "Characters marked [PLAYER-CONTROLLED] belong to the user. NEVER decide or "
    "write their actions, speech, thoughts, or feelings — not even for the ones "
    "who are not speaking right now. The user alone decides what a "
    "player-controlled character does, says, thinks, or feels; narrate only "
    "what they perceive and what the world does around them. GM-controlled "
    "characters (marked [GM-CONTROLLED]) may be played freely, but only from "
    "what they could know."
)

_FACT_KNOWN_COMMON = "common_knowledge"


class CastMember(BaseModel):
    """One character in the scene and who controls it."""

    entity_id: str = Field(description="Entity / character id (UUID string)")
    name: str = ""
    role: str = Field(default="npc", description="Free-form role label: pc / npc / monster / ...")
    controller: Literal["user", "gm"] = "gm"
    is_speaker: bool = False
    persona_id: str | None = Field(
        default=None,
        description="Standalone-character persona this incarnation is linked to (user characters only)",
    )
    persona_name: str | None = None


class Cast(BaseModel):
    """Every entity in the scene with its controller and speaker flag."""

    scene_id: str | None = None
    members: list[CastMember] = Field(default_factory=list)

    # -- queries -----------------------------------------------------------
    def speaker(self) -> CastMember | None:
        return next((m for m in self.members if m.is_speaker), None)

    def user_characters(self) -> list[CastMember]:
        return [m for m in self.members if m.controller == "user"]

    def gm_characters(self) -> list[CastMember]:
        return [m for m in self.members if m.controller == "gm"]

    def npc_members(self) -> list[CastMember]:
        return [m for m in self.gm_characters() if m.role.lower() in ("npc", "character", "pc-npc")]

    def by_id(self, entity_id: str | UUID | None) -> CastMember | None:
        key = str(entity_id) if entity_id is not None else ""
        return next((m for m in self.members if m.entity_id == key), None)

    def witness_ids(self) -> list[str]:
        """Ids of every cast member present — the default witnesses for facts
        and memories written during this turn (Task 8)."""
        return [m.entity_id for m in self.members]

    # -- rendering ---------------------------------------------------------
    def to_prompt_block(self) -> str:
        """Compact CAST block for prompt injection, agency rule included.

        Empty string when the cast has no members.
        """
        if not self.members:
            return ""
        lines: list[str] = []
        users = self.user_characters()
        gms = self.gm_characters()
        for m in users:
            bits = [f"[PLAYER-CONTROLLED] {m.name or m.entity_id}"]
            if m.is_speaker:
                bits.append("(SPEAKING NOW)")
            if m.persona_name:
                bits.append(f"persona: {m.persona_name}")
            elif m.persona_id:
                bits.append(f"persona: {m.persona_id}")
            lines.append("- " + " ".join(bits))
        for m in gms:
            bits = [f"[GM-CONTROLLED] {m.name or m.entity_id}"]
            if m.role and m.role.lower() not in ("character", "npc"):
                bits.append(f"({m.role})")
            lines.append("- " + " ".join(bits))
        rule = f"\n{AGENCY_RULE}"
        return "\n\nCAST (who is who in this scene):\n" + "\n".join(lines) + rule


# =============================================================================
# BUILD
# =============================================================================


def build_cast(
    *,
    controlled_ids: list[str] | None,
    speaker_id: str | UUID | None = None,
    actor_context: dict[str, Any] | None = None,
    entity_context: list[dict[str, Any]] | None = None,
    npc_profiles: dict[str, Any] | None = None,
    personas: dict[str, dict[str, Any]] | None = None,
    party: dict[str, Any] | list[dict[str, Any]] | None = None,
    scene_id: str | UUID | None = None,
) -> Cast:
    """Assemble the scene cast.

    Sources (Task 1):
    - the session's ``controlled_character_ids`` (user-controlled roster),
    - the scene's entities (``entity_context`` from ContextAssembly),
    - the party record (extra members not seen in entity_context),
    - NPC profiles (GM-controlled names for entities without a profile row).

    ``personas`` maps a controlled character id to ``{"persona_id",
    "persona_name"}`` (the persona-to-incarnation link, Task 4).
    """
    speaker_key = str(speaker_id) if speaker_id else ""
    personas = personas or {}
    members: dict[str, CastMember] = {}

    def _name_for(entity_id: str, fallback: str = "") -> str:
        for e in entity_context or []:
            if isinstance(e, dict) and str(e.get("id") or e.get("entity_id") or "") == entity_id:
                return str(e.get("name") or fallback)
        profile = (npc_profiles or {}).get(entity_id)
        if isinstance(profile, dict) and profile.get("name"):
            return str(profile["name"])
        return fallback

    # User-controlled characters first, in session order.
    for raw_id in controlled_ids or []:
        key = str(raw_id)
        if not key:
            continue
        persona = personas.get(key) or {}
        name = _name_for(key)
        if not name and isinstance(actor_context, dict) and str(actor_context.get("id") or "") == key:
            name = str(actor_context.get("name") or "")
        members[key] = CastMember(
            entity_id=key,
            name=name or key,
            role="pc",
            controller="user",
            is_speaker=key == speaker_key,
            persona_id=(persona.get("persona_id") or None) and str(persona["persona_id"]),
            persona_name=(persona.get("persona_name") or None) and str(persona["persona_name"]),
        )

    # If the speaker is not in the controlled roster (legacy sessions with
    # only ``character_id`` set), it is still user-controlled.
    if speaker_key and speaker_key not in members:
        members[speaker_key] = CastMember(
            entity_id=speaker_key,
            name=(
                str(actor_context.get("name") or "")
                if isinstance(actor_context, dict) and str(actor_context.get("id") or "") == speaker_key
                else _name_for(speaker_key)
            )
            or speaker_key,
            role="pc",
            controller="user",
            is_speaker=True,
        )

    # GM-controlled characters: character-typed scene entities + NPC profiles.
    def _add_gm(key: str, name: str, role: str) -> None:
        if not key or key in members:
            return
        members[key] = CastMember(
            entity_id=key,
            name=name or key,
            role=role or "npc",
            controller="gm",
            is_speaker=key == speaker_key,
        )

    for e in entity_context or []:
        if not isinstance(e, dict):
            continue
        key = str(e.get("id") or e.get("entity_id") or "")
        etype = str(e.get("entity_type") or e.get("type") or "").lower()
        if etype not in ("character", "npc", "monster", "pc"):
            continue
        _add_gm(key, str(e.get("name") or ""), etype if etype != "character" else "npc")

    for key, profile in (npc_profiles or {}).items():
        name = str(profile.get("name") or "") if isinstance(profile, dict) else ""
        _add_gm(str(key), name, "npc")

    # Party record: members not otherwise present (Task 1 source list).
    party_rows: list[dict[str, Any]] = []
    if isinstance(party, dict):
        raw = party.get("members") or party.get("member_ids") or []
        party_rows = [m if isinstance(m, dict) else {"id": m} for m in raw]
    elif isinstance(party, list):
        party_rows = [m if isinstance(m, dict) else {"id": m} for m in party]
    for row in party_rows:
        key = str(row.get("id") or row.get("entity_id") or row.get("member_id") or "")
        if not key or key in members:
            continue
        # A party member not flagged as user-controlled is GM-controlled.
        is_user = bool(row.get("controlled") or row.get("controller") == "user")
        members[key] = CastMember(
            entity_id=key,
            name=str(row.get("name") or key),
            role=str(row.get("role") or ("pc" if is_user else "npc")),
            controller="user" if is_user else "gm",
            is_speaker=key == speaker_key,
            persona_id=(row.get("persona_id") or None) and str(row["persona_id"]),
            persona_name=(row.get("persona_name") or None) and str(row["persona_name"]),
        )

    # Stable presentation: user characters first (session order preserved),
    # then GM characters.
    ordered = sorted(members.values(), key=lambda m: 0 if m.controller == "user" else 1)
    return Cast(scene_id=str(scene_id) if scene_id else None, members=ordered)


# =============================================================================
# FACT / MEMORY VISIBILITY (Task 8 — "who knows what")
# =============================================================================


def fact_visible_to(fact: dict[str, Any], npc_id: str | UUID) -> bool:
    """Can this NPC speak from this fact?

    A fact is visible when the NPC:
    - witnessed it (``witnesses`` carries the NPC's id),
    - was told (``told_to`` — top level or inside ``properties``/``metadata``),
    - or it is common knowledge. Facts with NO witness record at all —
      ingested lore, pre-cast legacy facts — default to common knowledge.

    ``witnesses`` may live on the row itself (typed field, once the write
    tools persist it) or inside ``properties``/``metadata``/``content``
    (the carriers that survive today's write paths).
    """
    npc_key = str(npc_id)
    if not npc_key:
        return True

    raw_props = fact.get("properties")
    props: dict[str, Any] = raw_props if isinstance(raw_props, dict) else {}
    raw_meta = fact.get("metadata")
    meta: dict[str, Any] = raw_meta if isinstance(raw_meta, dict) else {}
    raw_content = fact.get("content")
    content: dict[str, Any] = raw_content if isinstance(raw_content, dict) else {}
    raw_content_props = content.get("properties")
    content_props: dict[str, Any] = raw_content_props if isinstance(raw_content_props, dict) else {}

    for surface in (fact, content, props, meta, content_props):
        if npc_key in {str(value) for value in (surface.get("knowledge_excluded") or [])}:
            return False

    # Explicitly marked common knowledge wins over any witness restriction.
    for surface in (props, meta, content_props, fact, content):
        if surface.get(_FACT_KNOWN_COMMON) is True:
            return True

    witnesses: set[str] = set()
    told_to: set[str] = set()
    for surface in (fact, content, props, meta, content_props):
        for w in surface.get("witnesses") or []:
            witnesses.add(str(w))
        for t in surface.get("told_to") or []:
            told_to.add(str(t))

    if not witnesses and not told_to:
        # No witness record at all: ingested lore / legacy fact → common knowledge.
        return True
    return npc_key in witnesses or npc_key in told_to


def filter_visible_facts(facts: list[dict[str, Any]], npc_id: str | UUID) -> list[dict[str, Any]]:
    """Keep only the facts ``npc_id`` is allowed to know (Task 8)."""
    return [f for f in facts if isinstance(f, dict) and fact_visible_to(f, npc_id)]


# =============================================================================
# STATE TRANSPORT (UI layer → scene-loop nodes)
# =============================================================================


def cast_from_state(state: Any) -> Cast:
    """The cast the scene state carries.

    ``SceneState.cast`` is set on every turn from the session roster (the UI
    layer's ``get_scene_loop``), so the GM and the Narrator read the same
    roster before and after a backend restart.

    When the state carries no cast (the CLI, which has no session roster),
    the fallback is built from what the state alone knows: the speaker is
    user-controlled, every other character-typed entity or NPC profile is
    GM-controlled. The fallback cannot know the non-speaking user
    characters — that roster lives only in the session.
    """
    raw = getattr(state, "cast", None)
    if raw is not None:
        if isinstance(raw, Cast):
            return raw
        try:
            return Cast.model_validate(raw)
        except ValidationError:
            # A malformed cast degrades to the state-derived fallback below.
            log.debug("cast_from_state: state cast failed validation", exc_info=True)
    speaker_id = getattr(state, "actor_id", None)
    return build_cast(
        controlled_ids=[str(speaker_id)] if speaker_id else [],
        speaker_id=speaker_id,
        actor_context=getattr(state, "actor_context", None),
        entity_context=getattr(state, "entity_context", None),
        npc_profiles=getattr(state, "npc_profiles", None),
        scene_id=getattr(state, "scene_id", None),
    )
