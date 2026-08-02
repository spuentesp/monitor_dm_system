"""Read-only canonical visual context assembly for image generation.

LAYER: 2 (agents)
IMPORTS FROM: monitor_data (Layer 1) only

``assemble_image_context`` performs bounded reads through the existing
data-layer MCP tools and returns a frozen ``CanonicalVisualContext``:

  - approved visual identity payloads per anchor (canonical entity,
    incarnation, card default), with identity versions for provenance
  - canonical visual/current-state facts (with fact ids) per entity
  - approved primary/supporting generated assets usable as references

It never writes canon, assets, or identities, and only visual/current-state
facts are included — the full fact set is never dumped into image prompts.

The MCP read client is injectable for tests (the repo-wide ``FakeMCPClient``
matches the protocol); by default calls go through ``monitor_data.server``,
the same in-process path ``BaseAgent.call_tool`` uses.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any, Protocol
from uuid import UUID

import structlog
from pydantic import BaseModel, ConfigDict

from monitor_data.schemas.base import CanonLevel
from monitor_data.schemas.facts import FactStatus, FactType
from monitor_data.schemas.generated_assets import ApprovalStatus, ReferenceStatus
from monitor_data.schemas.visual_identity import VisualIdentity, VisualIdentityStatus

log = structlog.get_logger()

_VISUAL_METADATA_VALUES = frozenset({"appearance", "physical_appearance", "visual"})
_FACT_READ_LIMIT = 100
_ASSET_READ_LIMIT = 200


# ---------------------------------------------------------------------------
# Context model
# ---------------------------------------------------------------------------


class VisualFact(BaseModel):
    """A canonical visual/current-state fact retained for image prompts."""

    model_config = ConfigDict(frozen=True)

    fact_id: UUID
    statement: str
    entity_id: UUID | None = None


class ReferenceAsset(BaseModel):
    """An approved generated asset eligible as a prompt reference."""

    model_config = ConfigDict(frozen=True)

    asset_id: UUID
    reference_status: ReferenceStatus
    approval_status: ApprovalStatus = ApprovalStatus.APPROVED
    minio_key: str = ""


class IdentityVersion(BaseModel):
    """Provenance pointer: which immutable identity version was used."""

    model_config = ConfigDict(frozen=True)

    identity_id: UUID
    version: int


class CanonicalVisualContext(BaseModel):
    """Read-only canonical visual context consumed by the prompt builders."""

    model_config = ConfigDict(frozen=True)

    universe_id: UUID
    visual_identities: tuple[VisualIdentity, ...] = ()
    facts: tuple[VisualFact, ...] = ()
    reference_assets: tuple[ReferenceAsset, ...] = ()
    identity_versions: tuple[IdentityVersion, ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def source_fact_ids(self) -> tuple[UUID, ...]:
        """Fact ids backing this context, sorted for stable provenance."""
        return tuple(sorted({fact.fact_id for fact in self.facts}, key=str))


# ---------------------------------------------------------------------------
# MCP read client
# ---------------------------------------------------------------------------


class MCPReadClient(Protocol):
    """Minimal async MCP read surface (matches ``FakeMCPClient.call``)."""

    async def call(
        self,
        tool_name: str,
        params: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> Any: ...


class _ServerMCPReadClient:
    """Default read client: in-process data-layer server, like BaseAgent."""

    async def call(
        self,
        tool_name: str,
        params: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> Any:
        from monitor_data.server import call_tool as server_call_tool

        arguments = {**params, "agent_type": "ImageContextAssembler"}
        contents = await server_call_tool(tool_name, arguments)
        if not contents:
            return None
        text = contents[0].text
        if not isinstance(text, str):
            return text
        stripped = text.strip()
        if stripped and stripped[0] in '[{"':
            try:
                return json.loads(stripped)
            except json.JSONDecodeError:
                log.warning("image_context: JSON parse failed for tool %s", tool_name)
        return text or None


# ---------------------------------------------------------------------------
# Payload normalisation helpers
# ---------------------------------------------------------------------------


def _enum_str(value: Any) -> str:
    return str(getattr(value, "value", value) or "").lower()


def _as_uuid(value: Any) -> UUID | None:
    if value is None or value == "":
        return None
    try:
        return value if isinstance(value, UUID) else UUID(str(value))
    except (TypeError, ValueError):
        return None


def _as_identity(raw: Any) -> VisualIdentity | None:
    """Normalise a tool payload to an approved VisualIdentity, else None."""
    if raw is None:
        return None
    try:
        identity = raw if isinstance(raw, VisualIdentity) else VisualIdentity.model_validate(raw)
    except ValueError:
        return None
    if identity.status is not VisualIdentityStatus.APPROVED:
        return None
    return identity


def _has_visual_metadata(properties: Any) -> bool:
    if not isinstance(properties, Mapping):
        return False
    if properties.get("visual") is True or properties.get("is_visual") is True:
        return True
    for key in ("category", "domain", "kind", "type"):
        if _enum_str(properties.get(key)) in _VISUAL_METADATA_VALUES:
            return True
    tags = properties.get("tags")
    return isinstance(tags, (list, tuple, set, frozenset)) and any(
        _enum_str(tag) in _VISUAL_METADATA_VALUES for tag in tags
    )


def _as_payload(raw: Any) -> dict[str, Any] | None:
    """Normalise a tool payload item to a dict; None for unusable values."""
    if isinstance(raw, Mapping):
        return dict(raw)
    model_dump = getattr(raw, "model_dump", None)
    if callable(model_dump):
        payload = model_dump(mode="python")
        return dict(payload) if isinstance(payload, Mapping) else None
    return None


def _as_list(raw: Any, tool_name: str) -> list[Any]:
    """Normalise a list tool result; error strings/scalars become empty."""
    if raw is None:
        return []
    if isinstance(raw, (list, tuple)):
        return list(raw)
    log.warning(
        "image_context: tool %s returned a non-list payload (%s); skipping",
        tool_name,
        type(raw).__name__,
    )
    return []


def _as_visual_fact(raw: Any, entity_id: UUID) -> VisualFact | None:
    """Keep only active canonical visual/current-state facts."""
    payload = _as_payload(raw)
    if payload is None:
        return None
    if _enum_str(payload.get("canon_level")) != CanonLevel.CANON.value:
        return None
    if _enum_str(payload.get("status", FactStatus.ACTIVE)) != FactStatus.ACTIVE.value:
        return None
    fact_type = _enum_str(payload.get("fact_type"))
    if fact_type != FactType.STATE.value and not (
        fact_type == FactType.ATTRIBUTE.value and _has_visual_metadata(payload.get("properties"))
    ):
        return None
    fact_id = _as_uuid(payload.get("id"))
    statement = str(payload.get("statement") or "").strip()
    if fact_id is None or not statement:
        return None
    return VisualFact(fact_id=fact_id, statement=statement, entity_id=entity_id)


def _as_reference_asset(raw: Any) -> ReferenceAsset | None:
    """Keep only approved primary/supporting assets; rejected never pass."""
    payload = _as_payload(raw)
    if payload is None:
        return None
    asset_id = _as_uuid(payload.get("asset_id"))
    if asset_id is None:
        return None
    if _enum_str(payload.get("approval_status")) != ApprovalStatus.APPROVED.value:
        return None
    reference = _enum_str(payload.get("reference_status"))
    if reference not in (ReferenceStatus.PRIMARY.value, ReferenceStatus.SUPPORTING.value):
        return None
    return ReferenceAsset(
        asset_id=asset_id,
        reference_status=ReferenceStatus(reference),
        approval_status=ApprovalStatus.APPROVED,
        minio_key=str(payload.get("minio_key") or ""),
    )


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------


async def _read_identity(client: MCPReadClient, params: dict[str, Any]) -> VisualIdentity | None:
    raw = await client.call("mongodb_get_visual_identity", params)
    return _as_identity(raw)


async def _read_identities(
    client: MCPReadClient,
    *,
    universe_id: UUID,
    character_id: str | None,
    entity_ids: Sequence[UUID],
    warnings: list[str],
) -> list[VisualIdentity]:
    identities: dict[UUID, VisualIdentity] = {}
    approved = VisualIdentityStatus.APPROVED.value

    for entity_id in sorted(entity_ids, key=str):
        identity = await _read_identity(
            client,
            {"entity_id": str(entity_id), "universe_id": str(universe_id), "status": approved},
        )
        if identity is None:
            warnings.append(
                f"No approved visual identity found for entity {entity_id}; falling back to lower-priority sources."
            )
        else:
            identities[identity.identity_id] = identity

    if character_id is not None:
        incarnation = await _read_identity(
            client,
            {
                "character_id": character_id,
                "universe_id": str(universe_id),
                "status": approved,
            },
        )
        if incarnation is not None:
            identities[incarnation.identity_id] = incarnation
        card = await _read_identity(
            client,
            {"character_id": character_id, "status": approved, "card_default_only": True},
        )
        if card is not None and card.universe_id is None:
            identities[card.identity_id] = card
        if incarnation is None and card is None:
            warnings.append(
                f"No approved visual identity found for character {character_id}; card defaults will be used."
            )

    return [identities[key] for key in sorted(identities, key=str)]


async def _read_facts(
    client: MCPReadClient,
    *,
    universe_id: UUID,
    entity_ids: Sequence[UUID],
) -> list[VisualFact]:
    facts: dict[UUID, VisualFact] = {}
    for entity_id in sorted(entity_ids, key=str):
        raw = await client.call(
            "neo4j_list_facts",
            {
                "filters": {
                    "universe_id": str(universe_id),
                    "entity_id": str(entity_id),
                    "canon_level": CanonLevel.CANON.value,
                    "status": FactStatus.ACTIVE.value,
                    "limit": _FACT_READ_LIMIT,
                }
            },
        )
        for value in _as_list(raw, "neo4j_list_facts"):
            fact = _as_visual_fact(value, entity_id)
            if fact is not None:
                facts[fact.fact_id] = fact
    return [facts[key] for key in sorted(facts, key=str)]


async def _read_reference_assets(
    client: MCPReadClient,
    *,
    universe_id: UUID,
    character_id: str | None,
    entity_ids: Sequence[UUID],
    scene_id: UUID | None,
    conversation_id: UUID | None,
) -> list[ReferenceAsset]:
    scopes: list[dict[str, Any]] = [
        {"entity_id": str(entity_id), "universe_id": str(universe_id)} for entity_id in sorted(entity_ids, key=str)
    ]
    if character_id is not None:
        scopes.append({"character_id": character_id})
    if scene_id is not None:
        scopes.append({"scene_id": str(scene_id)})
    if conversation_id is not None:
        scopes.append({"conversation_id": str(conversation_id)})

    assets: dict[UUID, ReferenceAsset] = {}
    for scope in scopes:
        raw = await client.call(
            "mongodb_list_generated_assets",
            {
                "params": {
                    **scope,
                    "approval_status": ApprovalStatus.APPROVED.value,
                    "limit": _ASSET_READ_LIMIT,
                }
            },
        )
        for value in _as_list(raw, "mongodb_list_generated_assets"):
            asset = _as_reference_asset(value)
            if asset is not None:
                assets[asset.asset_id] = asset

    role_order = {ReferenceStatus.PRIMARY: 0, ReferenceStatus.SUPPORTING: 1}
    return sorted(assets.values(), key=lambda asset: (role_order[asset.reference_status], str(asset.asset_id)))


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------


async def assemble_image_context(
    *,
    universe_id: UUID | str,
    scene_id: UUID | str | None = None,
    conversation_id: UUID | str | None = None,
    character_id: str | None = None,
    entity_ids: Sequence[UUID | str] = (),
    mcp_client: MCPReadClient | None = None,
) -> CanonicalVisualContext:
    """Assemble a bounded canonical visual context using read tools only.

    Returns approved identities (with versions), visual/current-state canon
    facts (with fact ids), and approved reference assets — everything a
    caller needs to build a prompt and record GeneratedAsset provenance.
    Missing records are omitted with warnings; nothing is invented.
    """
    client = mcp_client or _ServerMCPReadClient()
    uid = _as_uuid(universe_id)
    if uid is None:
        raise ValueError(f"assemble_image_context: invalid universe_id {universe_id!r}")
    parsed_scene_id = _as_uuid(scene_id)
    parsed_conversation_id = _as_uuid(conversation_id)
    parsed_entity_ids = sorted(
        {parsed for raw in entity_ids if (parsed := _as_uuid(raw)) is not None},
        key=str,
    )

    warnings: list[str] = []
    identities = await _read_identities(
        client,
        universe_id=uid,
        character_id=character_id,
        entity_ids=parsed_entity_ids,
        warnings=warnings,
    )
    facts = await _read_facts(client, universe_id=uid, entity_ids=parsed_entity_ids)
    assets = await _read_reference_assets(
        client,
        universe_id=uid,
        character_id=character_id,
        entity_ids=parsed_entity_ids,
        scene_id=parsed_scene_id,
        conversation_id=parsed_conversation_id,
    )

    versions = {(identity.identity_id, identity.version) for identity in identities}
    log.debug(
        "image_context.assembled",
        universe_id=str(uid),
        identities=len(identities),
        facts=len(facts),
        reference_assets=len(assets),
    )
    return CanonicalVisualContext(
        universe_id=uid,
        visual_identities=tuple(identities),
        facts=tuple(facts),
        reference_assets=tuple(assets),
        identity_versions=tuple(
            IdentityVersion(identity_id=identity_id, version=version)
            for identity_id, version in sorted(versions, key=lambda item: (str(item[0]), item[1]))
        ),
        warnings=tuple(dict.fromkeys(warnings)),
    )


__all__ = [
    "CanonicalVisualContext",
    "IdentityVersion",
    "MCPReadClient",
    "ReferenceAsset",
    "VisualFact",
    "assemble_image_context",
]
