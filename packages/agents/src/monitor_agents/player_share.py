"""
ShareAgent — player-facing recap & handout sharing (CF-14 / G07).

LAYER: 2 (agents)
IMPORTS FROM: monitor_data (Layer 1 schemas + MCP tools), monitor_agents.cast
CALLED BY: UI backend routers (Layer 3)

The token is the credential: there are no player accounts in v1. This agent
is the single choke point between ``/share/*`` and storage — it resolves
tokens (unknown/revoked/expired all look the same to a prober), lists only
published artifacts, and resolves character-scoped spoilers **server-side**
using the same witnessed-facts visibility the narrator already uses
(``monitor_agents.cast.filter_visible_facts`` — shared with CF-6's
"what PC has witnessed" logic, never re-implemented here).

Nothing here writes to Neo4j; all persistence is Mongo via MCP tools.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, TypeVar
from uuid import UUID

import structlog
from monitor_agents.base import BaseAgent
from monitor_agents.cast import filter_visible_facts
from pydantic import BaseModel

from monitor_data.schemas.player_share import (
    PlayerArtifactSummary,
    PlayerShare,
    PlayerShareCharacter,
    PlayerShareCreate,
    PlayerView,
    ShareArtifactType,
    ShareSpoilerLevel,
    SharedArtifact,
    SharedArtifactCreate,
)

log = structlog.get_logger()

_ModelT = TypeVar("_ModelT", bound=BaseModel)


class ShareError(Exception):
    """Base class for share-link failures mapped to generic 404s."""


class ShareTokenError(ShareError):
    """Unknown, revoked, expired, or story-mismatched token."""


class ShareAccessError(ShareError):
    """Artifact is missing, foreign, unpublished, or not visible to the viewer."""


class ShareAgent(BaseAgent):
    """Publish/list/export player-facing artifacts behind a story share token."""

    def __init__(self, agent_id: str = "share-001") -> None:
        super().__init__(agent_type="ShareAgent", agent_id=agent_id)

    async def run(self) -> None:
        """Implemented for BaseAgent compliance; routes call the methods below."""

    # ------------------------------------------------------------------
    # Token lifecycle
    # ------------------------------------------------------------------

    async def resolve_share(self, token: str) -> PlayerShare:
        """Resolve a bearer token or raise ``ShareTokenError``.

        Unknown, revoked, and expired tokens all raise the same error so a
        prober cannot distinguish "never existed" from "was revoked".
        """
        raw = await self.call_tool("mongodb_get_player_share_by_token", {"token": token or ""})
        share = self._as_model(raw, PlayerShare)
        if share is None:
            raise ShareTokenError("unknown share token")
        if share.revoked:
            raise ShareTokenError("share token revoked")
        if share.expires_at is not None and share.expires_at <= datetime.now(UTC):
            raise ShareTokenError("share token expired")
        return share

    async def get_share_for_story(self, story_id: UUID) -> PlayerShare | None:
        """The story's active share token, or ``None`` when none exists."""
        raw = await self.call_tool("mongodb_get_player_share_for_story", {"story_id": str(story_id)})
        return self._as_model(raw, PlayerShare)

    async def ensure_share(self, *, universe_id: UUID, story_id: UUID, owner_id: str) -> PlayerShare:
        """The story's live link for this owner, minting one when absent.

        A link owned by someone else (or tied to another universe) is never
        reused — the new owner gets their own token.
        """
        share = await self.get_share_for_story(story_id)
        if share is not None and share.universe_id == universe_id and share.owner_id == owner_id:
            return share
        raw = await self.call_tool(
            "mongodb_create_player_share",
            {
                "params": PlayerShareCreate(
                    story_id=story_id,
                    universe_id=universe_id,
                    owner_id=owner_id,
                ).model_dump(mode="json"),
            },
        )
        created = self._as_model(raw, PlayerShare)
        if created is None:  # pragma: no cover - tool always returns the doc
            raise ShareError("failed to create share link")
        return created

    async def publish(
        self,
        *,
        universe_id: UUID,
        story_id: UUID,
        owner_id: str,
        artifact_type: ShareArtifactType,
        title: str,
        content: str,
        spoiler_level: ShareSpoilerLevel = ShareSpoilerLevel.PARTY,
        scope_character_id: UUID | None = None,
        source_fact_ids: list[UUID] | None = None,
        session_id: UUID | None = None,
    ) -> tuple[PlayerShare, SharedArtifact]:
        """Publish a recap/handout and ensure the story has a live share link.

        Returns ``(share, artifact)`` — the caller shows the share URL from
        ``share.token``. Mongo only; nothing here can touch canon.
        """
        share = await self.ensure_share(universe_id=universe_id, story_id=story_id, owner_id=owner_id)

        artifact = await self._create_artifact(
            universe_id=universe_id,
            story_id=story_id,
            owner_id=owner_id,
            artifact_type=artifact_type,
            title=title,
            content=content,
            spoiler_level=spoiler_level,
            scope_character_id=scope_character_id,
            source_fact_ids=source_fact_ids or [],
            session_id=session_id,
            published=True,
        )
        log.info(
            "artifact_published",
            artifact_id=str(artifact.id),
            story_id=str(story_id),
            artifact_type=artifact_type.value,
        )
        return share, artifact

    async def unpublish(self, *, artifact_id: UUID, universe_id: UUID, owner_id: str) -> bool:
        """Flip ``published`` off. False (never an exception) on a foreign ID."""
        raw = await self.call_tool(
            "mongodb_set_shared_artifact_published",
            {
                "artifact_id": str(artifact_id),
                "universe_id": str(universe_id),
                "owner_id": owner_id,
                "published": False,
            },
        )
        return bool(raw)

    async def revoke(self, *, story_id: UUID, universe_id: UUID, owner_id: str) -> bool:
        """Revoke every live token for the story. False on a foreign story."""
        raw = await self.call_tool(
            "mongodb_revoke_player_share",
            {
                "story_id": str(story_id),
                "universe_id": str(universe_id),
                "owner_id": owner_id,
            },
        )
        return bool(raw)

    # ------------------------------------------------------------------
    # Player-facing reads
    # ------------------------------------------------------------------

    async def build_player_view(
        self,
        story_id: UUID,
        token: str,
        character_id: UUID | None = None,
    ) -> PlayerView:
        """What this token may see for ``story_id``.

        Only published artifacts appear; character-scoped handouts are
        filtered server-side against witnessed facts (CF-14 acceptance).
        """
        share = await self.resolve_share(token)
        if share.story_id != story_id:
            raise ShareTokenError("token does not belong to this story")

        raw = await self.call_tool(
            "mongodb_list_shared_artifacts",
            {"story_id": str(story_id), "published_only": True},
        )
        # Defense in depth: even if the tool ignored published_only, a draft
        # must never reach a player (CF-14 acceptance: no draft/GM-only data).
        artifacts = [a for a in self._as_models(raw, SharedArtifact) if a.published]
        visible: list[PlayerArtifactSummary] = []
        for artifact in artifacts:
            if await self._artifact_visible(artifact, character_id):
                visible.append(
                    PlayerArtifactSummary(
                        id=artifact.id,
                        artifact_type=artifact.artifact_type,
                        title=artifact.title,
                        spoiler_level=artifact.spoiler_level,
                        updated_at=artifact.updated_at,
                    )
                )

        return PlayerView(
            story_id=story_id,
            character_id=character_id,
            artifacts=visible,
            characters=await self._party_roster(story_id),
        )

    async def get_visible_artifact(
        self,
        story_id: UUID,
        token: str,
        artifact_id: UUID,
        character_id: UUID | None = None,
        expected_type: ShareArtifactType | None = None,
    ) -> SharedArtifact:
        """Resolve one artifact for a token holder or raise ``ShareAccessError``.

        Drafts, foreign-story artifacts, wrong-type lookups (a recap id on the
        handout route), and invisible character-scoped handouts are all
        indistinguishable 404s from the outside.
        """
        share = await self.resolve_share(token)
        if share.story_id != story_id:
            raise ShareTokenError("token does not belong to this story")

        raw = await self.call_tool("mongodb_get_shared_artifact", {"artifact_id": str(artifact_id)})
        artifact = self._as_model(raw, SharedArtifact)
        if artifact is None:
            raise ShareAccessError("artifact not found")
        if artifact.story_id != story_id:
            raise ShareAccessError("artifact not found")
        if not artifact.published:
            raise ShareAccessError("artifact not published")
        if expected_type is not None and artifact.artifact_type is not expected_type:
            raise ShareAccessError("artifact not found")
        if not await self._artifact_visible(artifact, character_id):
            raise ShareAccessError("artifact not visible")
        return artifact

    def export_markdown(self, artifact: SharedArtifact) -> str:
        """Markdown export of a visible artifact (CF-2 step 5 / CF-6 step 4)."""
        lines = [f"# {artifact.title}", ""]
        if artifact.spoiler_level is ShareSpoilerLevel.CHARACTER:
            lines += [f"> Character-scoped {artifact.artifact_type.value}", ""]
        lines.append(artifact.content.strip())
        return "\n".join(lines).rstrip() + "\n"

    # ------------------------------------------------------------------
    # Spoiler resolution (CF-6 witnessed-facts logic, shared not copied)
    # ------------------------------------------------------------------

    async def _artifact_visible(self, artifact: SharedArtifact, character_id: UUID | None) -> bool:
        """Server-side visibility for one published artifact.

        - ``party`` → everyone holding the token.
        - ``character`` → the scoped PC always; any other PC only when they
          already witnessed **every** source fact (the handout then reveals
          nothing new). No facts recorded → scope only.
        """
        if artifact.spoiler_level is ShareSpoilerLevel.PARTY:
            return True
        if character_id is None:
            return False
        if artifact.scope_character_id is not None and artifact.scope_character_id == character_id:
            return True
        if not artifact.source_fact_ids:
            return False
        facts = await self._source_facts(artifact)
        if not facts or len(facts) < len(set(artifact.source_fact_ids)):
            # A referenced fact is gone → be conservative, do not show.
            return False
        # The witnessed-facts query/filter is CF-6's shared logic
        # (cast.filter_visible_facts, used by narrator/npc_voice).
        return len(filter_visible_facts(facts, character_id)) == len(facts)

    async def _source_facts(self, artifact: SharedArtifact) -> list[dict[str, Any]]:
        """Fetch the artifact's source facts (universe-scoped, id-matched)."""
        wanted = {str(f) for f in artifact.source_fact_ids}
        raw = await self.call_tool(
            "neo4j_list_facts",
            {
                "filters": {
                    "universe_id": str(artifact.universe_id),
                    "limit": 100,
                }
            },
        )
        facts = self._as_list(raw)
        return [f for f in facts if str(f.get("id")) in wanted]

    async def _party_roster(self, story_id: UUID) -> list[PlayerShareCharacter]:
        """Party members for the share page's character selector.

        Degrades to an empty roster (no selector) when Neo4j is unreachable —
        the artifact list itself must not fail because the roster did.
        """
        try:
            raw = await self.call_tool("neo4j_list_parties", {"story_id": str(story_id), "limit": 1})
            parties = self._as_list(raw)
            if not parties:
                return []
            members = parties[0].get("members") or []
            roster: list[PlayerShareCharacter] = []
            for member in members[:8]:
                entity_id = str(member.get("entity_id") or "")
                if not entity_id:
                    continue
                entity_raw = await self.call_tool("neo4j_get_entity", {"entity_id": entity_id})
                entity = self._as_dict(entity_raw)
                name = str((entity or {}).get("name") or f"Character {len(roster) + 1}")
                roster.append(PlayerShareCharacter(id=UUID(entity_id), name=name))
            return roster
        except ShareError:
            raise
        except Exception as exc:  # noqa: BLE001  # reason: roster is best-effort decoration
            log.warning("share_roster_unavailable", story_id=str(story_id), error=str(exc))
            return []

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _create_artifact(
        self,
        *,
        universe_id: UUID,
        story_id: UUID,
        owner_id: str,
        artifact_type: ShareArtifactType,
        title: str,
        content: str,
        spoiler_level: ShareSpoilerLevel,
        scope_character_id: UUID | None,
        source_fact_ids: list[UUID],
        session_id: UUID | None,
        published: bool,
    ) -> SharedArtifact:
        params = SharedArtifactCreate(
            story_id=story_id,
            universe_id=universe_id,
            owner_id=owner_id,
            artifact_type=artifact_type,
            title=title,
            content=content,
            spoiler_level=spoiler_level,
            scope_character_id=scope_character_id,
            source_fact_ids=source_fact_ids,
            session_id=session_id,
            published=published,
        )
        raw = await self.call_tool("mongodb_create_shared_artifact", {"params": params.model_dump(mode="json")})
        artifact = self._as_model(raw, SharedArtifact)
        if artifact is None:  # pragma: no cover - tool always returns the doc
            raise ShareError("failed to persist artifact")
        return artifact

    @staticmethod
    def _as_list(raw: Any) -> list[dict[str, Any]]:
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except json.JSONDecodeError:
                return []
        if not isinstance(raw, list):
            return []
        return [item for item in raw if isinstance(item, dict)]

    @staticmethod
    def _as_dict(raw: Any) -> dict[str, Any] | None:
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except json.JSONDecodeError:
                return None
        return raw if isinstance(raw, dict) else None

    @classmethod
    def _as_model(cls, raw: Any, model: type[_ModelT]) -> _ModelT | None:
        if isinstance(raw, model):
            return raw
        data = cls._as_dict(raw)
        if data is None:
            return None
        try:
            return model.model_validate(data)
        except Exception:  # noqa: BLE001  # reason: malformed tool payload = miss
            return None

    @classmethod
    def _as_models(cls, raw: Any, model: type[_ModelT]) -> list[_ModelT]:
        items = cls._as_list(raw)
        models: list[_ModelT] = []
        for item in items:
            try:
                models.append(model.model_validate(item))
            except Exception as exc:  # noqa: BLE001  # reason: skip malformed rows, keep the rest
                log.debug("share_artifact_row_skipped", error=str(exc))
                continue
        return models
