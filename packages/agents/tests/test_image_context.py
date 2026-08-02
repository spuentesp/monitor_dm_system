"""Read-only canonical image-context assembly tests (Task 4, Layer 2).

Uses the repo-wide ``FakeMCPClient`` (tests/conftest.py) to stub the
data-layer read tools: ``mongodb_get_visual_identity``, ``neo4j_list_facts``
and ``mongodb_list_generated_assets``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from tests.conftest import FakeMCPClient

from monitor_agents.image_context import (
    CanonicalVisualContext,
    assemble_image_context,
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
_UNIVERSE_ID = UUID("10000000-0000-0000-0000-000000000001")
_ENTITY_ID = UUID("20000000-0000-0000-0000-000000000001")
_SCENE_ID = UUID("40000000-0000-0000-0000-000000000001")
_CHARACTER_ID = "dinah-lance"


def _identity(**overrides: Any) -> VisualIdentity:
    payload: dict[str, Any] = {
        "identity_id": uuid4(),
        "character_id": _CHARACTER_ID,
        "version": 1,
        "description": "A poised martial artist.",
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
        "character_id": _CHARACTER_ID,
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


def _fact_dict(
    statement: str,
    *,
    fact_type: str = "state",
    canon_level: str = "canon",
    status: str = "active",
    properties: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "id": str(uuid4()),
        "universe_id": str(_UNIVERSE_ID),
        "statement": statement,
        "fact_type": fact_type,
        "magnitude": 1,
        "scope": "local",
        "canon_level": canon_level,
        "knowledge_scope": "world",
        "confidence": 1.0,
        "authority": "system",
        "status": status,
        "created_at": _NOW.isoformat(),
        "replaces": None,
        "properties": properties,
        "entity_ids": [str(_ENTITY_ID)],
        "source_ids": [],
        "snippet_ids": [],
        "scene_ids": [],
    }


def _fake_mcp(
    *,
    canonical: VisualIdentity | None = None,
    incarnation: VisualIdentity | None = None,
    card: VisualIdentity | None = None,
    facts: list[dict[str, Any]] | None = None,
    assets: list[GeneratedAsset] | None = None,
) -> FakeMCPClient:
    """Fake MCP client dispatching on (tool_name, params).

    ``assemble_image_context`` calls ``client.call(...)``; like the existing
    agent tests (``agent.call_tool = fake_mcp.call_tool``) we route the fake's
    mock-style ``call_tool`` proxy (which supports ``side_effect`` dispatch
    and call recording) into the ``call`` attribute.
    """
    client = FakeMCPClient()

    def dispatch(tool_name: str, params: dict[str, Any]) -> Any:
        if tool_name == "mongodb_get_visual_identity":
            if params.get("entity_id") is not None:
                identity = canonical
            elif params.get("universe_id") is not None:
                identity = incarnation
            else:
                identity = card
            return identity.model_dump(mode="json") if identity is not None else None
        if tool_name == "neo4j_list_facts":
            return list(facts or [])
        if tool_name == "mongodb_list_generated_assets":
            return [asset.model_dump(mode="json") for asset in (assets or [])]
        raise NotImplementedError(f"unexpected tool {tool_name}")

    client.call_tool.side_effect = dispatch
    client.call = client.call_tool  # type: ignore[method-assign]
    return client


# ---------------------------------------------------------------------------
# Regression: card lookup must not be shadowed by a higher-version
# incarnation (Task 4 review, finding 1)
# ---------------------------------------------------------------------------


def _real_get_visual_identity(
    identities: list[VisualIdentity],
    params: dict[str, Any],
) -> dict[str, Any] | None:
    """Model the REAL ``mongodb_get_visual_identity`` semantics.

    The tool builds its anchor query with ``include_nulls=False``: any
    parameter left as None is OMITTED from the query, so a character_id-only
    lookup matches identities from every anchor (card defaults AND
    incarnations), and the highest version wins.  With
    ``card_default_only=True`` the tool matches the explicit null anchor
    (``include_nulls=True`` semantics).
    """
    card_default_only = bool(params.get("card_default_only"))
    query: dict[str, Any] = {}
    for key in ("character_id", "entity_id", "universe_id"):
        value = params.get(key)
        if card_default_only or value is not None:
            query[key] = value
    status = params.get("status", "approved")

    def matches(identity: VisualIdentity) -> bool:
        if identity.status.value != status:
            return False
        for key, value in query.items():
            actual = getattr(identity, key)
            if value is None:
                if actual is not None:
                    return False
            elif actual is None or str(actual) != str(value):
                return False
        return True

    hits = [identity for identity in identities if matches(identity)]
    if not hits:
        return None
    best = max(hits, key=lambda identity: identity.version)
    return best.model_dump(mode="json")


@pytest.mark.asyncio
async def test_card_lookup_is_not_shadowed_by_higher_version_incarnation() -> None:
    """Real tool semantics: without an explicit null-anchor query, a card
    lookup matches all anchors and returns the highest version — an approved
    incarnation shadows the card default, which is then silently dropped.
    The card lookup must ask for the card-default anchor explicitly.
    """
    other_universe = UUID("90000000-0000-0000-0000-000000000009")
    card = _identity(version=1, description="Card default description.")
    # Approved incarnation for a DIFFERENT universe, with a higher version.
    cross_universe_incarnation = _identity(
        universe_id=other_universe,
        version=5,
        description="Cross-universe incarnation.",
    )
    identities = [card, cross_universe_incarnation]

    client = FakeMCPClient()

    def dispatch(tool_name: str, params: dict[str, Any]) -> Any:
        if tool_name == "mongodb_get_visual_identity":
            return _real_get_visual_identity(identities, params)
        if tool_name == "neo4j_list_facts":
            return []
        if tool_name == "mongodb_list_generated_assets":
            return []
        raise NotImplementedError(f"unexpected tool {tool_name}")

    client.call_tool.side_effect = dispatch
    client.call = client.call_tool  # type: ignore[method-assign]

    context = await assemble_image_context(
        universe_id=_UNIVERSE_ID,
        character_id=_CHARACTER_ID,
        mcp_client=client,
    )

    identity_ids = {identity.identity_id for identity in context.visual_identities}
    assert card.identity_id in identity_ids
    assert cross_universe_incarnation.identity_id not in identity_ids
    assert not any("card defaults will be used" in warning for warning in context.warnings)


# ---------------------------------------------------------------------------
# Defensive readers: malformed tool payloads never crash assembly
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_error_string_and_scalar_tool_payloads_are_tolerated() -> None:
    """If a tool returns an error string (or a scalar inside a list), the
    readers must skip it instead of crashing with AttributeError."""
    card = _identity()
    client = FakeMCPClient()

    def dispatch(tool_name: str, params: dict[str, Any]) -> Any:
        if tool_name == "mongodb_get_visual_identity":
            return card.model_dump(mode="json")
        if tool_name == "neo4j_list_facts":
            return "Tool execution failed: connection refused"
        if tool_name == "mongodb_list_generated_assets":
            return [42, "not-an-asset", None]
        raise NotImplementedError(f"unexpected tool {tool_name}")

    client.call_tool.side_effect = dispatch
    client.call = client.call_tool  # type: ignore[method-assign]

    context = await assemble_image_context(
        universe_id=_UNIVERSE_ID,
        character_id=_CHARACTER_ID,
        entity_ids=(_ENTITY_ID,),
        mcp_client=client,
    )

    assert {identity.identity_id for identity in context.visual_identities} == {card.identity_id}
    assert context.facts == ()
    assert context.reference_assets == ()


# ---------------------------------------------------------------------------
# Model shape
# ---------------------------------------------------------------------------


def test_context_model_is_frozen_and_empty_by_default() -> None:
    context = CanonicalVisualContext(universe_id=_UNIVERSE_ID)
    assert context.visual_identities == ()
    assert context.facts == ()
    assert context.reference_assets == ()
    assert context.identity_versions == ()
    with pytest.raises(ValidationError):
        context.warnings = ("mutate",)  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Happy path: identities + facts + assets + provenance
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_assembles_identities_facts_assets_and_provenance() -> None:
    canonical = _identity(
        character_id=None,
        entity_id=_ENTITY_ID,
        universe_id=_UNIVERSE_ID,
        version=4,
        source=VisualIdentitySource.CANON,
    )
    incarnation = _identity(universe_id=_UNIVERSE_ID, version=2)
    card = _identity(version=1)
    state_fact = _fact_dict("Her jacket is torn.")
    visual_attribute = _fact_dict(
        "Her eyes are grey.",
        fact_type="attribute",
        properties={"category": "appearance"},
    )
    primary = _asset(
        entity_id=_ENTITY_ID,
        universe_id=_UNIVERSE_ID,
        reference_status=ReferenceStatus.PRIMARY,
    )
    supporting = _asset(reference_status=ReferenceStatus.SUPPORTING)
    client = _fake_mcp(
        canonical=canonical,
        incarnation=incarnation,
        card=card,
        facts=[state_fact, visual_attribute],
        assets=[supporting, primary],
    )

    context = await assemble_image_context(
        universe_id=_UNIVERSE_ID,
        character_id=_CHARACTER_ID,
        entity_ids=(_ENTITY_ID,),
        mcp_client=client,
    )

    assert context.universe_id == _UNIVERSE_ID
    identity_ids = {identity.identity_id for identity in context.visual_identities}
    assert identity_ids == {canonical.identity_id, incarnation.identity_id, card.identity_id}

    statements = {fact.statement for fact in context.facts}
    assert statements == {"Her jacket is torn.", "Her eyes are grey."}
    assert all(fact.fact_id for fact in context.facts)
    assert all(fact.entity_id == _ENTITY_ID for fact in context.facts)

    assert [asset.reference_status for asset in context.reference_assets] == [
        ReferenceStatus.PRIMARY,
        ReferenceStatus.SUPPORTING,
    ]

    versions = {(v.identity_id, v.version) for v in context.identity_versions}
    assert versions == {
        (canonical.identity_id, 4),
        (incarnation.identity_id, 2),
        (card.identity_id, 1),
    }


# ---------------------------------------------------------------------------
# Fact filtering: only visual/current-state canon facts
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_filters_non_visual_and_non_canon_facts() -> None:
    keep_state = _fact_dict("The door is broken.")
    keep_visual = _fact_dict(
        "Her hair is singed.",
        fact_type="attribute",
        properties={"tags": ["visual"]},
    )
    drop_relationship = _fact_dict("Dinah is allied with Oliver.", fact_type="relationship")
    drop_plain_attribute = _fact_dict("Dinah has 5 HP.", fact_type="attribute")
    drop_proposed = _fact_dict("Rumour says she dyes her hair.", canon_level="proposed")
    drop_superseded = _fact_dict("Her arm was broken.", status="superseded")
    client = _fake_mcp(
        facts=[
            keep_state,
            keep_visual,
            drop_relationship,
            drop_plain_attribute,
            drop_proposed,
            drop_superseded,
        ]
    )

    context = await assemble_image_context(
        universe_id=_UNIVERSE_ID,
        entity_ids=(_ENTITY_ID,),
        mcp_client=client,
    )

    statements = {fact.statement for fact in context.facts}
    assert statements == {"The door is broken.", "Her hair is singed."}


# ---------------------------------------------------------------------------
# Asset filtering: rejected/pending never become references
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rejected_pending_and_unroled_assets_are_excluded() -> None:
    approved_primary = _asset(reference_status=ReferenceStatus.PRIMARY)
    rejected = _asset(
        approval_status=ApprovalStatus.REJECTED,
        reference_status=ReferenceStatus.PRIMARY,
    )
    pending = _asset(
        approval_status=ApprovalStatus.PENDING,
        reference_status=ReferenceStatus.SUPPORTING,
    )
    unroled = _asset(reference_status=ReferenceStatus.NONE)
    client = _fake_mcp(assets=[rejected, pending, unroled, approved_primary])

    context = await assemble_image_context(
        universe_id=_UNIVERSE_ID,
        character_id=_CHARACTER_ID,
        mcp_client=client,
    )

    assert [asset.asset_id for asset in context.reference_assets] == [approved_primary.asset_id]


# ---------------------------------------------------------------------------
# Scoping, missing data, and minimal calls
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scene_and_conversation_scope_asset_queries() -> None:
    conversation_id = uuid4()
    client = _fake_mcp()

    await assemble_image_context(
        universe_id=_UNIVERSE_ID,
        scene_id=_SCENE_ID,
        conversation_id=conversation_id,
        character_id=_CHARACTER_ID,
        entity_ids=(_ENTITY_ID,),
        mcp_client=client,
    )

    asset_queries = [params for name, params in client._call_tool_all_args if name == "mongodb_list_generated_assets"]
    scopes = [query["params"] for query in asset_queries]
    assert any(scope.get("scene_id") == str(_SCENE_ID) for scope in scopes)
    assert any(scope.get("conversation_id") == str(conversation_id) for scope in scopes)
    assert any(scope.get("entity_id") == str(_ENTITY_ID) for scope in scopes)
    assert any(scope.get("character_id") == _CHARACTER_ID for scope in scopes)
    assert all(scope.get("approval_status") == "approved" for scope in scopes)


@pytest.mark.asyncio
async def test_missing_identity_is_tolerated_with_warning() -> None:
    client = _fake_mcp(canonical=None)

    context = await assemble_image_context(
        universe_id=_UNIVERSE_ID,
        entity_ids=(_ENTITY_ID,),
        mcp_client=client,
    )

    assert context.visual_identities == ()
    assert any("visual identity" in warning for warning in context.warnings)


@pytest.mark.asyncio
async def test_character_only_assembly_reads_no_facts() -> None:
    card = _identity()
    incarnation = _identity(universe_id=_UNIVERSE_ID, version=2)
    client = _fake_mcp(card=card, incarnation=incarnation)

    context = await assemble_image_context(
        universe_id=_UNIVERSE_ID,
        character_id=_CHARACTER_ID,
        mcp_client=client,
    )

    assert {identity.identity_id for identity in context.visual_identities} == {
        card.identity_id,
        incarnation.identity_id,
    }
    assert context.facts == ()
    fact_calls = [name for name, _ in client._call_tool_all_args if name == "neo4j_list_facts"]
    assert fact_calls == []


@pytest.mark.asyncio
async def test_universe_scoped_facts_query_uses_canon_filter() -> None:
    client = _fake_mcp()

    await assemble_image_context(
        universe_id=_UNIVERSE_ID,
        entity_ids=(_ENTITY_ID,),
        mcp_client=client,
    )

    fact_calls = [params for name, params in client._call_tool_all_args if name == "neo4j_list_facts"]
    assert len(fact_calls) == 1
    filters = fact_calls[0]["filters"]
    assert filters["universe_id"] == str(_UNIVERSE_ID)
    assert filters["entity_id"] == str(_ENTITY_ID)
    assert filters["canon_level"] == "canon"
    assert filters["status"] == "active"


@pytest.mark.asyncio
async def test_superseded_identity_is_dropped_defensively() -> None:
    superseded = _identity(status=VisualIdentityStatus.SUPERSEDED)
    client = _fake_mcp(card=superseded)

    context = await assemble_image_context(
        universe_id=_UNIVERSE_ID,
        character_id=_CHARACTER_ID,
        mcp_client=client,
    )

    assert context.visual_identities == ()
    assert context.identity_versions == ()
