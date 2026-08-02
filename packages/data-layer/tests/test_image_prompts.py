"""Canon-aware prompt assembly tests (Task 4, Layer 1).

The prompt builders are pure functions.  They receive a character-like input
(mapping or attribute object) plus a duck-typed canonical visual context —
the real ``CanonicalVisualContext`` lives in Layer 2, so these tests use
``SimpleNamespace`` doubles to pin the documented attribute contract:

    context.visual_identities  — iterable of VisualIdentity (or mappings)
    context.facts              — iterable with ``fact_id``/``statement``
    context.reference_assets   — iterable with ``asset_id`` and optional
                                 ``approval_status`` / ``reference_status``
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

from monitor_data.llm.image_prompts import (
    ImagePrompt,
    build_portrait_prompt,
    build_scene_prompt,
)
from monitor_data.schemas.generated_assets import (
    ApprovalStatus,
    AssetType,
    GeneratedAsset,
    ReferenceStatus,
)
from monitor_data.schemas.visual_identity import (
    VisualIdentity,
    VisualIdentitySource,
    VisualIdentityStatus,
)

_NOW = datetime(2026, 7, 31, tzinfo=UTC)


def _identity(**overrides: Any) -> VisualIdentity:
    payload: dict[str, Any] = {
        "identity_id": uuid4(),
        "character_id": "dinah-lance",
        "version": 1,
        "description": "A poised martial artist.",
        "hair": "shoulder-length blonde hair",
        "eyes": "blue eyes",
        "signature_attire": "a black leather jacket",
        "source": VisualIdentitySource.MANUAL,
        "status": VisualIdentityStatus.APPROVED,
        "created_at": _NOW,
        "updated_at": _NOW,
    }
    payload.update(overrides)
    return VisualIdentity(**payload)


def _asset(**overrides: Any) -> GeneratedAsset:
    payload: dict[str, Any] = {
        "asset_id": uuid4(),
        "asset_type": AssetType.PORTRAIT,
        "minio_key": "generated/reference.png",
        "byte_size": 100,
        "character_id": "dinah-lance",
        "prompt": "reference",
        "provider_id": "test-provider",
        "provider_model": "test-model",
        "approval_status": ApprovalStatus.APPROVED,
        "reference_status": ReferenceStatus.SUPPORTING,
        "created_at": _NOW,
        "updated_at": _NOW,
    }
    payload.update(overrides)
    return GeneratedAsset(**payload)


def _fact(
    fact_id: UUID,
    statement: str,
    entity_id: UUID | None = None,
    *,
    status: str | None = None,
    canon_level: str | None = None,
    fact_type: str | None = None,
    properties: dict[str, Any] | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        fact_id=fact_id,
        statement=statement,
        entity_id=entity_id,
        status=status,
        canon_level=canon_level,
        fact_type=fact_type,
        properties=properties,
    )


def _context(
    *,
    identities: tuple[VisualIdentity, ...] = (),
    facts: tuple[Any, ...] = (),
    assets: tuple[Any, ...] = (),
) -> SimpleNamespace:
    """Duck-typed stand-in for the Layer 2 CanonicalVisualContext."""
    return SimpleNamespace(
        visual_identities=identities,
        facts=facts,
        reference_assets=assets,
    )


_CHARACTER = {
    "name": "Black Canary",
    "description": "A singer with a brown bob.",
    "personality": "Bold, dry-witted, protective of her team.",
}


# ---------------------------------------------------------------------------
# ImagePrompt model shape
# ---------------------------------------------------------------------------


def test_image_prompt_defaults() -> None:
    prompt = ImagePrompt(positive="a portrait")
    assert prompt.positive == "a portrait"
    assert prompt.negative == ""
    assert prompt.reference_asset_ids == []
    assert prompt.source_fact_ids == []
    assert prompt.warnings == []


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_portrait_prompt_is_deterministic_for_reordered_inputs() -> None:
    identity = _identity()
    fact_a = _fact(UUID("00000000-0000-0000-0000-000000000001"), "Her jacket is torn.")
    fact_b = _fact(UUID("00000000-0000-0000-0000-000000000002"), "Her left hand is bandaged.")
    primary = _asset(
        asset_id=UUID("00000000-0000-0000-0000-000000000010"),
        reference_status=ReferenceStatus.PRIMARY,
    )
    supporting = _asset(
        asset_id=UUID("00000000-0000-0000-0000-000000000011"),
        reference_status=ReferenceStatus.SUPPORTING,
    )

    one = build_portrait_prompt(
        dict(_CHARACTER),
        _context(identities=(identity,), facts=(fact_b, fact_a), assets=(supporting, primary)),
    )
    two = build_portrait_prompt(
        dict(_CHARACTER),
        _context(identities=(identity,), facts=(fact_a, fact_b), assets=(primary, supporting)),
    )

    assert one == two
    assert one.source_fact_ids == [str(fact_a.fact_id), str(fact_b.fact_id)]
    assert one.reference_asset_ids == [str(primary.asset_id), str(supporting.asset_id)]


def test_scene_prompt_is_deterministic() -> None:
    messages = [
        {"role": "player", "content": "I kick open the saloon doors."},
        {"role": "narrator", "content": "Every head turns toward you."},
    ]
    context = _context(identities=(_identity(),))
    first = build_scene_prompt(list(messages), context)
    second = build_scene_prompt(list(messages), context)
    assert first == second


# ---------------------------------------------------------------------------
# Precedence: canonical entity > incarnation > card identity > card fallback
# ---------------------------------------------------------------------------


def test_canonical_identity_overrides_incarnation_and_card_with_warnings() -> None:
    entity_id, universe_id = uuid4(), uuid4()
    canonical = _identity(
        character_id=None,
        entity_id=entity_id,
        universe_id=universe_id,
        version=4,
        hair="long platinum-blonde hair",
        source=VisualIdentitySource.CANON,
    )
    incarnation = _identity(
        entity_id=None,
        universe_id=universe_id,
        version=2,
        hair="cropped black hair",
    )
    card_identity = _identity(hair="brown bob")

    result = build_portrait_prompt(
        dict(_CHARACTER),
        _context(identities=(card_identity, incarnation, canonical)),
    )

    assert "long platinum-blonde hair" in result.positive
    assert "cropped black hair" not in result.positive
    assert "brown bob" not in result.positive
    hair_warnings = [w for w in result.warnings if "hair" in w]
    assert any("incarnation identity" in w for w in hair_warnings)
    assert any("card identity" in w for w in hair_warnings)


def test_approved_incarnation_identity_overrides_card_when_canon_absent() -> None:
    incarnation = _identity(universe_id=uuid4(), version=3, eyes="bright green eyes")
    card_identity = _identity(eyes="brown eyes")

    result = build_portrait_prompt(
        dict(_CHARACTER),
        _context(identities=(card_identity, incarnation)),
    )

    assert "bright green eyes" in result.positive
    assert "brown eyes" not in result.positive
    assert any("eyes" in w and "card identity" in w for w in result.warnings)


def test_card_identity_overrides_card_description_fallback() -> None:
    card_identity = _identity(description="A scar runs down her left cheek.")
    character = {**_CHARACTER, "description": "Her face is unmarked."}

    result = build_portrait_prompt(character, _context(identities=(card_identity,)))

    assert "A scar runs down her left cheek." in result.positive
    assert "Her face is unmarked." not in result.positive
    assert any("description" in w and "card defaults" in w for w in result.warnings)


def test_draft_identity_is_not_used_for_prompt_text() -> None:
    draft = _identity(status=VisualIdentityStatus.DRAFT, hair="neon pink mohawk")

    result = build_portrait_prompt(dict(_CHARACTER), _context(identities=(draft,)))

    assert "neon pink mohawk" not in result.positive
    # Card fallback fills the gap instead.
    assert _CHARACTER["description"] in result.positive


# ---------------------------------------------------------------------------
# Incarnation identities carrying an entity_id stay tier 1 (Task 4 review)
# ---------------------------------------------------------------------------


def test_incarnation_with_entity_id_does_not_usurp_canonical_tier() -> None:
    """The schema allows incarnation anchors with an optional entity_id
    (character_id + universe_id + entity_id).  Such an identity must stay an
    incarnation (tier 1): canonical precedence and its conflict warning are
    preserved.
    """
    entity_id, universe_id = uuid4(), uuid4()
    canonical = _identity(
        character_id=None,
        entity_id=entity_id,
        universe_id=universe_id,
        version=1,
        hair="long platinum-blonde hair",
        source=VisualIdentitySource.CANON,
    )
    incarnation_with_entity = _identity(
        entity_id=entity_id,
        universe_id=universe_id,
        version=9,
        hair="cropped black hair",
    )

    result = build_portrait_prompt(
        dict(_CHARACTER),
        _context(identities=(incarnation_with_entity, canonical)),
    )

    assert "long platinum-blonde hair" in result.positive
    assert "cropped black hair" not in result.positive
    hair_warnings = [w for w in result.warnings if "hair" in w]
    assert any("incarnation identity" in w for w in hair_warnings)


def test_incarnation_with_entity_id_still_overrides_card_default() -> None:
    entity_id, universe_id = uuid4(), uuid4()
    incarnation_with_entity = _identity(
        entity_id=entity_id,
        universe_id=universe_id,
        version=3,
        eyes="bright green eyes",
    )
    card_identity = _identity(eyes="brown eyes")

    result = build_portrait_prompt(
        dict(_CHARACTER),
        _context(identities=(card_identity, incarnation_with_entity)),
    )

    assert "bright green eyes" in result.positive
    assert "brown eyes" not in result.positive
    assert any("eyes" in w and "incarnation identity" in w for w in result.warnings)
    assert any("eyes" in w and "card identity" in w for w in result.warnings)


# ---------------------------------------------------------------------------
# Card fallback and empty context
# ---------------------------------------------------------------------------


def test_card_description_and_personality_fallback_without_identities() -> None:
    result = build_portrait_prompt(dict(_CHARACTER), _context())

    assert "Character portrait of Black Canary." in result.positive
    assert _CHARACTER["description"] in result.positive
    assert f"Personality: {_CHARACTER['personality']}" in result.positive
    assert result.reference_asset_ids == []
    assert result.source_fact_ids == []
    assert result.warnings == []


def test_character_object_input_is_accepted() -> None:
    character = SimpleNamespace(**_CHARACTER)

    result = build_portrait_prompt(character, _context())

    assert "Character portrait of Black Canary." in result.positive
    assert _CHARACTER["description"] in result.positive


def test_empty_context_means_card_fallback_only() -> None:
    result = build_portrait_prompt(dict(_CHARACTER), None)

    assert _CHARACTER["description"] in result.positive
    assert result.reference_asset_ids == []
    assert result.source_fact_ids == []


def test_missing_character_name_uses_generic_subject() -> None:
    result = build_portrait_prompt({}, _context())
    assert result.positive.startswith("Character portrait of a fictional character.")


# ---------------------------------------------------------------------------
# Reference assets: rejected never appear
# ---------------------------------------------------------------------------


def test_rejected_and_pending_assets_never_become_references() -> None:
    primary = _asset(reference_status=ReferenceStatus.PRIMARY)
    supporting = _asset(reference_status=ReferenceStatus.SUPPORTING)
    rejected = _asset(
        approval_status=ApprovalStatus.REJECTED,
        reference_status=ReferenceStatus.PRIMARY,
    )
    pending = _asset(
        approval_status=ApprovalStatus.PENDING,
        reference_status=ReferenceStatus.SUPPORTING,
    )
    no_role = _asset(reference_status=ReferenceStatus.NONE)

    result = build_portrait_prompt(
        dict(_CHARACTER),
        _context(assets=(rejected, supporting, no_role, pending, primary)),
    )

    assert result.reference_asset_ids == [str(primary.asset_id), str(supporting.asset_id)]
    assert str(rejected.asset_id) not in result.reference_asset_ids
    assert str(pending.asset_id) not in result.reference_asset_ids
    assert str(no_role.asset_id) not in result.reference_asset_ids


# ---------------------------------------------------------------------------
# Scene prompt: 3000-char excerpt cap
# ---------------------------------------------------------------------------


def test_scene_excerpt_is_capped_at_3000_characters() -> None:
    filler = "x" * 2990
    messages = [
        {"role": "narrator", "content": "DISCARD-ME " + filler},
        {"role": "player", "content": "END"},
    ]
    result = build_scene_prompt(messages, _context())

    excerpt = result.positive.split("Scene excerpt:\n", 1)[1].split("\n\nStyle:", 1)[0]
    assert len(excerpt) <= 3000
    assert excerpt.endswith("player: END")
    assert "DISCARD-ME" not in excerpt
    assert any("3,000" in w or "3000" in w for w in result.warnings)


def test_scene_excerpt_cut_drops_partial_first_line() -> None:
    """A mid-line cut must trim to the first newline: no partial first line."""
    messages = [
        {"role": "narrator", "content": "OLD " + "x" * 4000},
        {"role": "player", "content": "END"},
    ]
    result = build_scene_prompt(messages, _context())

    excerpt = result.positive.split("Scene excerpt:\n", 1)[1].split("\n\nStyle:", 1)[0]
    # The narrator line was cut mid-line; the whole partial line is dropped.
    assert excerpt == "player: END"
    assert len(excerpt) <= 3000
    assert any("3,000" in w or "3000" in w for w in result.warnings)


def test_scene_excerpt_cut_on_line_boundary_keeps_full_3000() -> None:
    """When the cut lands exactly on a line boundary, no line is dropped."""
    boundary_line = "player: " + "y" * 2980  # 2988 chars; + "\n" + "player: END" = 3000
    messages = [
        {"role": "narrator", "content": "DISCARD-ME"},
        {"role": "player", "content": "y" * 2980},
        {"role": "player", "content": "END"},
    ]
    result = build_scene_prompt(messages, _context())

    excerpt = result.positive.split("Scene excerpt:\n", 1)[1].split("\n\nStyle:", 1)[0]
    assert len(excerpt) == 3000
    assert excerpt == boundary_line + "\nplayer: END"
    assert any("3,000" in w or "3000" in w for w in result.warnings)


def test_scene_prompt_includes_identity_and_facts() -> None:
    entity_id = uuid4()
    canonical = _identity(
        character_id=None,
        entity_id=entity_id,
        universe_id=uuid4(),
        hair="long platinum-blonde hair",
        source=VisualIdentitySource.CANON,
    )
    fact = _fact(uuid4(), "The bar mirror is cracked.", entity_id=entity_id)
    messages = [{"role": "narrator", "content": "The bar goes quiet."}]

    result = build_scene_prompt(messages, _context(identities=(canonical,), facts=(fact,)))

    assert "long platinum-blonde hair" in result.positive
    assert "The bar mirror is cracked." in result.positive
    assert "The bar goes quiet." in result.positive
    assert result.source_fact_ids == [str(fact.fact_id)]


def test_scene_prompt_without_messages_still_renders() -> None:
    result = build_scene_prompt([], _context())
    assert "Cinematic scene illustration" in result.positive
    assert result.warnings == []


def test_scene_messages_accept_text_and_speaker_keys() -> None:
    messages = [
        {"entity_name": "Dinah", "text": "Not another step."},
        {"speaker_role": "narrator", "content": "The room holds its breath."},
    ]
    result = build_scene_prompt(messages, _context())
    assert "Dinah: Not another step." in result.positive
    assert "narrator: The room holds its breath." in result.positive


# ---------------------------------------------------------------------------
# Task 11 — canon-anchored scene composition (full provenance + exclusivity)
# ---------------------------------------------------------------------------


def _canonical_identity(**overrides: Any) -> VisualIdentity:
    """An approved canonical (entity-level) identity for a scene subject."""
    payload = {
        "identity_id": uuid4(),
        "character_id": None,
        "entity_id": uuid4(),
        "universe_id": uuid4(),
        "version": 3,
        "description": "A scarred veteran in a leather duster.",
        "hair": "salt-and-pepper buzz cut",
        "eyes": "grey eyes",
        "signature_attire": "charcoal duster with brass buttons",
        "source": VisualIdentitySource.CANON,
        "status": VisualIdentityStatus.APPROVED,
        "created_at": _NOW,
        "updated_at": _NOW,
    }
    payload.update(overrides)
    return VisualIdentity(**payload)


def test_scene_composition_renders_all_anchors_facts_and_provenance() -> None:
    """Scenario: a canonical location, two subject entities (approved canonical
    identities with primary portraits), an equipment fact, and an injury fact —
    all must reach the rendered prompt AND the structured provenance
    (reference_asset_ids, source_fact_ids).

    A scene prompt groups identities by anchor; the canonical location
    and each subject render their own Visual identity block. Every approved
    primary/supporting asset surfaces in ``reference_asset_ids``. Facts
    with matching ids surface in ``source_fact_ids`` in deterministic order.
    """
    location = _canonical_identity(
        entity_id=uuid4(),
        description="A rain-soaked neon arcade in a derelict mall.",
    )
    subject_a = _canonical_identity(
        entity_id=uuid4(),
        hair="short auburn hair",
        eyes="hazel eyes",
        signature_attire="torn bomber jacket",
    )
    subject_b = _canonical_identity(
        entity_id=uuid4(),
        hair="shaved head",
        eyes="amber eyes",
        signature_attire="olive fatigues",
    )
    equipment_fact = _fact(
        UUID("00000000-0000-0000-0000-0000000000a1"),
        "Subject A wields a compact pulse pistol.",
        entity_id=subject_a.entity_id,
    )
    injury_fact = _fact(
        UUID("00000000-0000-0000-0000-0000000000a2"),
        "Subject A's right arm is bandaged.",
        entity_id=subject_a.entity_id,
    )
    location_fact = _fact(
        UUID("00000000-0000-0000-0000-0000000000a3"),
        "Rain pools across the arcade floor.",
        entity_id=location.entity_id,
    )
    primary_a = _asset(
        asset_id=UUID("00000000-0000-0000-0000-0000000000b1"),
        entity_id=subject_a.entity_id,
        reference_status=ReferenceStatus.PRIMARY,
    )
    primary_b = _asset(
        asset_id=UUID("00000000-0000-0000-0000-0000000000b2"),
        entity_id=subject_b.entity_id,
        reference_status=ReferenceStatus.PRIMARY,
    )
    supporting_loc = _asset(
        asset_id=UUID("00000000-0000-0000-0000-0000000000b3"),
        entity_id=location.entity_id,
        reference_status=ReferenceStatus.SUPPORTING,
    )
    messages = [{"role": "narrator", "content": "The neon flickers twice."}]
    ctx = _context(
        identities=(location, subject_a, subject_b),
        facts=(equipment_fact, injury_fact, location_fact),
        assets=(primary_a, primary_b, supporting_loc),
    )

    result = build_scene_prompt(messages, ctx)

    # Every anchor reaches the prompt (description + a visual field each).
    assert "rain-soaked neon arcade" in result.positive
    assert "short auburn hair" in result.positive
    assert "shaved head" in result.positive
    # Each fact surfaces in the "Current visual facts" section.
    assert "compact pulse pistol" in result.positive
    assert "right arm is bandaged" in result.positive
    assert "Rain pools across the arcade floor" in result.positive
    # Provenance: every approved reference appears in the deterministic order.
    assert result.reference_asset_ids == [
        str(primary_a.asset_id),
        str(primary_b.asset_id),
        str(supporting_loc.asset_id),
    ]
    # Provenance: every fact id is recorded, sorted for determinism.
    assert result.source_fact_ids == sorted(
        [str(equipment_fact.fact_id), str(injury_fact.fact_id), str(location_fact.fact_id)]
    )


def test_scene_prompt_excludes_unrelated_rejected_and_superseded() -> None:
    """Exclusivity: facts unrelated to the scene (relationship / non-visual /
    superseded / proposed) and rejected/pending references must NOT reach
    the rendered prompt or the provenance lists.

    Facts here carry explicit ``status`` / ``canon_level`` fields so the
    prompt builder's defensive filter can drop them — the same fields the
    upstream ``image_context._as_visual_fact`` filter checks.
    """
    keep_state = _fact(
        uuid4(),
        "The escalator is jammed.",
        entity_id=uuid4(),
        status="active",
        canon_level="canon",
        fact_type="state",
    )
    keep_visual = _fact(
        uuid4(),
        "Her hair is singed.",
        entity_id=uuid4(),
        status="active",
        canon_level="canon",
        fact_type="attribute",
        properties={"category": "appearance"},
    )
    drop_relationship = _fact(
        uuid4(),
        "Dinah is allied with Oliver.",
        entity_id=uuid4(),
        status="active",
        canon_level="canon",
        fact_type="relationship",
    )
    drop_plain_attribute = _fact(
        uuid4(),
        "Dinah has 5 HP.",
        entity_id=uuid4(),
        status="active",
        canon_level="canon",
        fact_type="attribute",
    )
    drop_proposed = _fact(
        uuid4(),
        "Rumour says she dyes her hair.",
        entity_id=uuid4(),
        status="active",
        canon_level="proposed",
        fact_type="state",
    )
    drop_superseded = _fact(
        uuid4(),
        "Her arm was broken.",
        entity_id=uuid4(),
        status="superseded",
        canon_level="canon",
        fact_type="state",
    )

    approved_primary = _asset(reference_status=ReferenceStatus.PRIMARY)
    approved_supporting = _asset(reference_status=ReferenceStatus.SUPPORTING)
    rejected = _asset(
        approval_status=ApprovalStatus.REJECTED,
        reference_status=ReferenceStatus.PRIMARY,
    )
    pending = _asset(
        approval_status=ApprovalStatus.PENDING,
        reference_status=ReferenceStatus.SUPPORTING,
    )
    no_role = _asset(reference_status=ReferenceStatus.NONE)

    ctx = _context(
        facts=(
            keep_state,
            keep_visual,
            drop_relationship,
            drop_plain_attribute,
            drop_proposed,
            drop_superseded,
        ),
        assets=(approved_primary, approved_supporting, rejected, pending, no_role),
    )

    result = build_scene_prompt([], ctx)

    # Kept facts reach the prompt; excluded facts never appear.
    assert "escalator is jammed" in result.positive
    assert "hair is singed" in result.positive
    assert "allied with Oliver" not in result.positive
    assert "5 HP" not in result.positive
    assert "Rumour says" not in result.positive
    assert "arm was broken" not in result.positive

    # Source-fact provenance only carries the kept facts.
    kept_fact_ids = {str(keep_state.fact_id), str(keep_visual.fact_id)}
    assert set(result.source_fact_ids) == kept_fact_ids
    assert all(
        fid not in result.source_fact_ids
        for fid in (
            str(drop_relationship.fact_id),
            str(drop_plain_attribute.fact_id),
            str(drop_proposed.fact_id),
            str(drop_superseded.fact_id),
        )
    )

    # Reference provenance only carries the approved primary/supporting assets.
    assert result.reference_asset_ids == [
        str(approved_primary.asset_id),
        str(approved_supporting.asset_id),
    ]
    assert str(rejected.asset_id) not in result.reference_asset_ids
    assert str(pending.asset_id) not in result.reference_asset_ids
    assert str(no_role.asset_id) not in result.reference_asset_ids
