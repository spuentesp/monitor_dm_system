"""Deterministic image-suggestion heuristics (Task 9).

LAYER: 2 (agents)
IMPORTS FROM: monitor_data (Layer 1) schemas only
CALLED BY: loops/scene_loop.py (narrate node)

A scene turn can *suggest* an image worth generating — a new canonical
location, an NPC's first entrance, an explicit appearance-state change, or
climax pacing. Suggestions are pure data (``ImageSuggestion`` models) carried
on ``SceneState.image_suggestions`` → narrate result → done-frame metadata;
the frontend renders them as chips and only an explicit click generates.
Nothing here calls a provider, a database, or a WebSocket.

Everything is deterministic: the same inputs produce the same suggestions
with the same ``suggestion_id`` (uuid5 derived from reason + subjects +
source turn — never random).

Rate limits (spec):
- at most one suggestion per three turns — triggers are only evaluated on
  cadence-window turns (``turn_number % SUGGESTION_CADENCE_TURNS == 0``), and
  at most one suggestion is emitted per evaluation;
- at most two suggestions per scene — enforced against ``prior_suggestions``.
"""

from __future__ import annotations

from typing import Any, Literal, Sequence
from uuid import NAMESPACE_URL, UUID, uuid5

import structlog
from monitor_data.schemas.generated_assets import AssetType
from pydantic import BaseModel, Field

log = structlog.get_logger()

#: Evaluate triggers only on every Nth turn → at most one suggestion / 3 turns.
SUGGESTION_CADENCE_TURNS = 3
#: Hard cap of suggestions emitted per scene.
MAX_SUGGESTIONS_PER_SCENE = 2

ImageSuggestionReason = Literal["location_change", "npc_entry", "visual_state_change", "climax"]


class ImageSuggestion(BaseModel):
    """A single "generate an image?" hint surfaced to the player."""

    suggestion_id: UUID
    asset_type: AssetType
    subject_entity_ids: list[UUID] = Field(default_factory=list)
    reason: ImageSuggestionReason
    aspect_ratio: str = "16:9"
    source_turn_id: str


def resolution_flags_appearance_change(resolution: dict[str, Any] | None) -> bool:
    """True when the resolver explicitly declared an appearance-state change.

    The signal is deliberately explicit — either an ``appearance_change``
    flag or an effect string mentioning "appearance" — so ordinary narration
    never triggers portrait suggestions by accident.
    """
    if not isinstance(resolution, dict):
        return False
    if resolution.get("appearance_change"):
        return True
    effects = resolution.get("effects") or []
    return any(isinstance(e, str) and "appearance" in e.lower() for e in effects)


def _coerce_prior(prior: Sequence[ImageSuggestion | dict[str, Any]]) -> list[ImageSuggestion]:
    """Normalize prior suggestions (models or post-checkpoint JSON dicts)."""
    out: list[ImageSuggestion] = []
    for item in prior:
        if isinstance(item, ImageSuggestion):
            out.append(item)
            continue
        try:
            out.append(ImageSuggestion.model_validate(item))
        except Exception:
            log.debug("image_suggestions.unparseable_prior_dropped")
    return out


def derive_turn_signals(
    entity_context: Sequence[Any] | None,
    *,
    actor_id: UUID | None = None,
) -> dict[str, Any]:
    """Derive ``location_name`` + ``npcs_present`` from the per-turn entity context.

    ``SceneState.turn_context`` is never populated by the graph in production
    (no ``build_turn_context`` node exists), so the location/NPC signals the
    image-suggestion heuristics need are not available. This function fills
    the gap by reading directly from ``entity_context``, which ``load_context``
    does populate.

    - ``location_name`` is the first location-typed entity, with the
      ``"current"`` state_tag winning over plain order. Case-insensitive on
      ``entity_type``.
    - ``npcs_present`` is a list of ``{"entity_id", "name"}`` for every
      character entity except the player (matched by ``actor_id`` or by a
      ``properties.role == "PC"`` marker).
    """
    signals: dict[str, Any] = {"location_name": "", "npcs_present": []}
    if not isinstance(entity_context, (list, tuple)):
        return signals

    current_location: str | None = None
    first_location: str | None = None
    npcs: list[dict[str, Any]] = []
    actor_key = str(actor_id) if actor_id is not None else None

    for entity in entity_context:
        if not isinstance(entity, dict):
            continue
        etype = str(entity.get("entity_type") or entity.get("type") or "").lower()
        name = str(entity.get("name") or entity.get("canonical_name") or "").strip()
        entity_id = entity.get("id")

        if etype in {"location", "place", "region"} and name:
            tags = entity.get("state_tags") or entity.get("tags") or []
            tags_lc = {str(t).lower() for t in tags if t is not None}
            if "current" in tags_lc:
                current_location = name
            elif first_location is None:
                first_location = name

        elif etype in {"character", "npc", "person"} and name and entity_id is not None:
            entity_key = str(entity_id)
            if actor_key is not None and entity_key == actor_key:
                continue
            properties = entity.get("properties") or {}
            role = str(properties.get("role") or "").upper()
            if role == "PC":
                continue
            npcs.append({"entity_id": entity_key, "name": name})

    signals["location_name"] = current_location or first_location or ""
    signals["npcs_present"] = npcs
    return signals


def _subject_uuid(raw: Any, *, seed: str) -> UUID | None:
    """Parse an entity-id-ish value; derive a deterministic uuid5 when absent."""
    if raw:
        try:
            return raw if isinstance(raw, UUID) else UUID(str(raw))
        except (TypeError, ValueError):
            pass
    if seed:
        return uuid5(NAMESPACE_URL, f"monitor:image-suggestion/subject:{seed}")
    return None


def _suggestion_id(reason: str, subjects: list[UUID], source_turn_id: str) -> UUID:
    subject_key = ",".join(sorted(str(s) for s in subjects))
    return uuid5(NAMESPACE_URL, f"monitor:image-suggestion:{reason}:{subject_key}:{source_turn_id}")


def _already_suggested(prior: list[ImageSuggestion], reason: str, subjects: list[UUID]) -> bool:
    wanted = set(subjects)
    for s in prior:
        if s.reason != reason:
            continue
        if not wanted or wanted & set(s.subject_entity_ids):
            return True
    return False


def _location_subject(location_name: str, entity_context: Sequence[dict[str, Any]]) -> UUID:
    """The current location's canonical entity id (or a deterministic stand-in)."""
    for entity in entity_context:
        if not isinstance(entity, dict):
            continue
        if str(entity.get("entity_type") or "").lower() != "location":
            continue
        if str(entity.get("name") or "").strip().lower() != location_name.lower():
            continue
        subject = _subject_uuid(entity.get("id"), seed="")
        if subject is not None:
            return subject
    return uuid5(NAMESPACE_URL, f"monitor:image-suggestion/location:{location_name.lower()}")


def compute_image_suggestions(
    *,
    turn_id: str,
    turn_number: int,
    pacing: dict[str, Any] | None = None,
    turn_context: dict[str, Any] | None = None,
    entity_context: Sequence[dict[str, Any]] = (),
    actor_id: UUID | None = None,
    appearance_state_changed: bool = False,
    prior_suggestions: Sequence[ImageSuggestion | dict[str, Any]] = (),
) -> list[ImageSuggestion]:
    """Compute 0..1 image suggestions for a scene turn. Pure and deterministic.

    Args:
        turn_id: id of the turn being narrated (becomes ``source_turn_id``).
        turn_number: 1-based number of this turn within the scene.
        pacing: deterministic pacing signal (``{"tempo": …, "phase": …}``).
        turn_context: structured scene situation (location_name, npcs_present).
        entity_context: canonical entities in scope (used to anchor subjects).
        actor_id: the player character's entity id (appearance-change subject).
        appearance_state_changed: explicit appearance-change signal for this
            turn (see ``resolution_flags_appearance_change``).
        prior_suggestions: suggestions already emitted this scene (dedupe +
            per-scene cap).

    Returns:
        ``[]`` or a single ``ImageSuggestion``. Triggers are evaluated in
        spec order: location_change → npc_entry → visual_state_change → climax.
    """
    prior = _coerce_prior(prior_suggestions)

    # Rate limits: scene cap, then the 3-turn cadence window.
    if len(prior) >= MAX_SUGGESTIONS_PER_SCENE:
        return []
    if turn_number < SUGGESTION_CADENCE_TURNS or turn_number % SUGGESTION_CADENCE_TURNS != 0:
        return []

    ctx = turn_context if isinstance(turn_context, dict) else {}

    def _emit(
        reason: ImageSuggestionReason,
        asset_type: AssetType,
        subjects: list[UUID],
        aspect_ratio: str,
    ) -> list[ImageSuggestion]:
        suggestion = ImageSuggestion(
            suggestion_id=_suggestion_id(reason, subjects, turn_id),
            asset_type=asset_type,
            subject_entity_ids=subjects,
            reason=reason,
            aspect_ratio=aspect_ratio,
            source_turn_id=turn_id,
        )
        log.debug(
            "image_suggestions.emitted",
            reason=reason,
            asset_type=str(asset_type),
            source_turn_id=turn_id,
        )
        return [suggestion]

    # 1. New canonical location (first time this location anchors the scene).
    location_name = str(ctx.get("location_name") or "").strip()
    if location_name:
        subject = _location_subject(location_name, entity_context)
        if not _already_suggested(prior, "location_change", [subject]):
            return _emit("location_change", AssetType.LOCATION, [subject], "16:9")

    # 2. First NPC entrance (first time this NPC is visually anchored).
    npcs = ctx.get("npcs_present") or []
    for npc in npcs:
        if not isinstance(npc, dict):
            continue
        npc_subject = _subject_uuid(
            npc.get("entity_id") or npc.get("id"),
            seed=f"npc:{str(npc.get('name') or '').strip().lower()}",
        )
        if npc_subject is None:
            continue
        if not _already_suggested(prior, "npc_entry", [npc_subject]):
            return _emit("npc_entry", AssetType.PORTRAIT, [npc_subject], "1:1")

    # 3. Explicit appearance-state change on the player character.
    if appearance_state_changed and actor_id is not None:
        if not _already_suggested(prior, "visual_state_change", [actor_id]):
            return _emit("visual_state_change", AssetType.PORTRAIT, [actor_id], "1:1")

    # 4. Climax pacing — one establishing scene image per scene.
    phase = str((pacing or {}).get("phase") or "")
    if phase == "peak" and not _already_suggested(prior, "climax", []):
        return _emit("climax", AssetType.SCENE, [], "16:9")

    return []
