"""
Tests for VisualIdentity schemas (Layer 1, Task 1).

A VisualIdentity is a structured, canon-aware description of a subject's
appearance. It supports three anchor shapes:

  - card default:       character_id only (no universe context)
  - incarnation:        character_id + universe_id, optional entity_id
  - canonical entity:   entity_id + universe_id

Validation rules:

  - exactly one anchor must be present
  - entity_id is not allowed without universe_id
  - at most 20 distinguishing features
  - status transitions follow draft -> approved -> superseded
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from monitor_data.schemas.visual_identity import (
    VisualIdentity,
    VisualIdentityCreate,
    VisualIdentitySource,
    VisualIdentityStatus,
    VisualIdentityUpdate,
    transition_visual_identity_status,
)


# =============================================================================
# HELPERS
# =============================================================================


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _base_payload(**overrides):
    """Return a baseline VisualIdentityCreate payload for tests."""
    payload = {
        "character_id": "char-1",
        "description": "A weathered archer with keen eyes.",
        "species_or_type": "human",
        "apparent_age": "early 30s",
        "build": "lean, athletic",
        "hair": "dark brown, shoulder-length, tied back",
        "eyes": "green",
        "skin_or_surface": "sun-tanned",
        "signature_attire": "leather jerkin, green cloak",
        "distinguishing_features": ["scar over left eyebrow", "silver earring"],
        "palette": ["forest green", "leather brown"],
        "style_hint": "painterly fantasy portrait",
        "source": VisualIdentitySource.MANUAL,
    }
    payload.update(overrides)
    return payload


# =============================================================================
# ENUM VALUES
# =============================================================================


class TestVisualIdentityEnums:
    def test_visual_identity_source_values(self) -> None:
        assert VisualIdentitySource.MANUAL == "manual"
        assert VisualIdentitySource.CARD_IMPORT == "card_import"
        assert VisualIdentitySource.CANON == "canon"
        assert VisualIdentitySource.AI_EXTRACTED == "ai_extracted"

    def test_visual_identity_status_values(self) -> None:
        assert VisualIdentityStatus.DRAFT == "draft"
        assert VisualIdentityStatus.APPROVED == "approved"
        assert VisualIdentityStatus.SUPERSEDED == "superseded"


# =============================================================================
# VALID ANCHORS
# =============================================================================


class TestValidAnchors:
    def test_card_default_anchor(self) -> None:
        """character_id only is a valid card-default identity."""
        ident = VisualIdentityCreate(**_base_payload())
        assert ident.character_id == "char-1"
        assert ident.universe_id is None
        assert ident.entity_id is None
        assert ident.source == VisualIdentitySource.MANUAL

    def test_incarnation_anchor(self) -> None:
        """character_id + universe_id is a valid incarnation identity."""
        universe = uuid4()
        ident = VisualIdentityCreate(**_base_payload(universe_id=universe))
        assert ident.character_id == "char-1"
        assert ident.universe_id == universe
        assert ident.entity_id is None

    def test_canonical_entity_anchor(self) -> None:
        """entity_id + universe_id is a valid canonical-entity identity."""
        universe = uuid4()
        entity = uuid4()
        ident = VisualIdentityCreate(
            **_base_payload(
                character_id=None,
                universe_id=universe,
                entity_id=entity,
                source=VisualIdentitySource.CANON,
            )
        )
        assert ident.character_id is None
        assert ident.universe_id == universe
        assert ident.entity_id == entity
        assert ident.source == VisualIdentitySource.CANON

    def test_incarnation_with_entity_id(self) -> None:
        """Incarnation identities may also carry an entity_id."""
        universe = uuid4()
        entity = uuid4()
        ident = VisualIdentityCreate(
            **_base_payload(universe_id=universe, entity_id=entity)
        )
        assert ident.character_id == "char-1"
        assert ident.universe_id == universe
        assert ident.entity_id == entity


# =============================================================================
# VALIDATION FAILURES
# =============================================================================


class TestAnchorValidation:
    def test_reject_identity_with_no_anchor(self) -> None:
        """A VisualIdentity with no character_id and no entity_id must be rejected."""
        with pytest.raises(ValidationError) as exc:
            VisualIdentityCreate(
                **_base_payload(
                    character_id=None,
                    universe_id=None,
                    entity_id=None,
                )
            )
        assert "anchor" in str(exc.value).lower()

    def test_reject_entity_id_without_universe_id(self) -> None:
        """entity_id requires universe_id as its canonical anchor."""
        with pytest.raises(ValidationError) as exc:
            VisualIdentityCreate(
                **_base_payload(
                    character_id=None,
                    universe_id=None,
                    entity_id=uuid4(),
                )
            )
        assert "universe_id" in str(exc.value).lower()

    def test_reject_more_than_20_distinguishing_features(self) -> None:
        """distinguishing_features is capped at 20 entries."""
        features = [f"feature-{i}" for i in range(21)]
        with pytest.raises(ValidationError) as exc:
            VisualIdentityCreate(**_base_payload(distinguishing_features=features))
        assert "distinguishing_features" in str(exc.value).lower()

    def test_accept_exactly_20_distinguishing_features(self) -> None:
        """Boundary: 20 features is allowed."""
        features = [f"feature-{i}" for i in range(20)]
        ident = VisualIdentityCreate(**_base_payload(distinguishing_features=features))
        assert len(ident.distinguishing_features) == 20


# =============================================================================
# STATUS TRANSITIONS
# =============================================================================


class TestStatusTransitions:
    def test_draft_to_approved(self) -> None:
        assert (
            transition_visual_identity_status(
                VisualIdentityStatus.DRAFT, VisualIdentityStatus.APPROVED
            )
            is True
        )

    def test_approved_to_superseded(self) -> None:
        assert (
            transition_visual_identity_status(
                VisualIdentityStatus.APPROVED, VisualIdentityStatus.SUPERSEDED
            )
            is True
        )

    def test_draft_to_superseded_is_invalid(self) -> None:
        assert (
            transition_visual_identity_status(
                VisualIdentityStatus.DRAFT, VisualIdentityStatus.SUPERSEDED
            )
            is False
        )

    def test_superseded_to_anything_is_invalid(self) -> None:
        assert (
            transition_visual_identity_status(
                VisualIdentityStatus.SUPERSEDED, VisualIdentityStatus.APPROVED
            )
            is False
        )
        assert (
            transition_visual_identity_status(
                VisualIdentityStatus.SUPERSEDED, VisualIdentityStatus.DRAFT
            )
            is False
        )

    def test_self_transition_is_invalid(self) -> None:
        assert (
            transition_visual_identity_status(
                VisualIdentityStatus.DRAFT, VisualIdentityStatus.DRAFT
            )
            is False
        )


# =============================================================================
# VISUAL IDENTITY (RESPONSE) MODEL
# =============================================================================


class TestVisualIdentityResponse:
    def test_defaults(self) -> None:
        universe = uuid4()
        ident = VisualIdentity(
            created_at=_now(),
            updated_at=_now(),
            universe_id=universe,
            character_id="char-1",
        )
        assert ident.version == 1
        assert ident.status == VisualIdentityStatus.DRAFT
        assert ident.approved_reference_asset_ids == []
        assert ident.distinguishing_features == []
        assert ident.palette == []

    def test_update_only_mutates_allowed_fields(self) -> None:
        payload = VisualIdentityUpdate(
            description="Updated description.",
            hair="white",
            status=VisualIdentityStatus.APPROVED,
        )
        assert payload.model_dump(exclude_none=True) == {
            "description": "Updated description.",
            "hair": "white",
            "status": VisualIdentityStatus.APPROVED,
        }
