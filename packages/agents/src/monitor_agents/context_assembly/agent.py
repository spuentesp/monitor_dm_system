"""
ContextAssembly Agent — assembles multi-source context for a scene turn.

LAYER: 2 (agents)
IMPORTS FROM: monitor_data (Layer 1), monitor_agents.prompts

Responsibilities:
- Formulate retrieval queries from player action (via DSPy QueryFormulationModule)
- Fetch entities from Neo4j (via MCP tool)
- Fetch memories + snippets from Qdrant (via MCP tool)
- Rank and summarise raw context (deterministic scoring, no LLM call)

This agent is called from scene_loop.load_context().
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import logging
import time
from typing import Any, cast
from uuid import UUID

from monitor_data.config import settings
from monitor_data.schemas.llm_config import ModelRole

from monitor_agents.base import BaseAgent
from monitor_agents.context_assembly.context_assembly import QueryFormulationModule
from monitor_agents.token_budget import TokenBudget, count_tokens, truncate_to_tokens
from monitor_agents.utils.dialogue_context_support import (
    build_dialogue_turn_windows,
    compose_dialogue_focus_terms,
    conversation_turns_to_memory_items,
    dialogue_windows_to_memory_items,
    is_dialogue_action,
    rank_conversation_turns,
    rank_dialogue_windows,
)
from monitor_agents.utils.query_traversal import (
    build_traversal_mask,
    collect_traversal_query_terms,
    get_counterpart_entity_id,
    score_candidate_relationship,
)
from monitor_agents.utils.runtime_profile_support import (
    build_profile_context,
    expand_query_with_profile,
    normalize_source_profile,
    rank_snippets_with_profile,
)
from monitor_agents.utils.source_scope_support import (
    append_scope_terms_to_query,
    derive_source_scope,
    rank_snippets_with_source_scope,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Deterministic ranking helpers (replace LLM-based ContextAssemblyModule)
# ---------------------------------------------------------------------------


def _extract_terms(text: str) -> set[str]:
    """Extract normalized, significant terms from text for overlap scoring."""
    import re

    # Split on whitespace and punctuation, lowercase, drop short tokens.
    tokens = re.split(r"[\W_]+", (text or "").lower())
    return {t for t in tokens if len(t) >= 3}


def _score_item(
    text: str,
    action_terms: set[str],
    profile_terms: set[str],
) -> float:
    """Score a context item by term overlap with action + profile terms."""
    item_terms = _extract_terms(text)
    if not item_terms:
        return 0.0
    action_overlap = len(action_terms & item_terms) / max(len(action_terms), 1)
    profile_overlap = len(profile_terms & item_terms) / max(len(profile_terms), 1)
    # Weight action overlap more heavily (0.7 vs 0.3).
    return action_overlap * 0.7 + profile_overlap * 0.3


def _entity_to_text(entity: dict[str, Any]) -> str:
    """Flatten an entity dict into a single readable string for scoring."""
    parts: list[str] = []
    name = entity.get("name", "")
    if name:
        parts.append(str(name))
    entity_type = entity.get("type", "") or entity.get("entity_type", "")
    if entity_type:
        parts.append(f"({entity_type})")
    description = entity.get("description", "") or entity.get("notes", "")
    if description:
        parts.append(str(description)[:200])
    # Include key attributes.
    attrs = entity.get("attributes", {}) or entity.get("properties", {})
    if isinstance(attrs, dict):
        for k, v in list(attrs.items())[:5]:
            if v:
                parts.append(f"{k}: {v}")
    return " ".join(parts)


class ContextAssembly(BaseAgent):
    """
    Assembles ranked, relevance-filtered context from all three data sources.

    Stateless — each call fetches fresh context from the databases.
    """

    def __init__(self, agent_id: str = "context-assembly-1") -> None:
        super().__init__(agent_type="ContextAssembly", agent_id=agent_id)
        self._query_formulator = QueryFormulationModule()
        self._token_budget = TokenBudget(ModelRole.STANDARD)

    async def run(self) -> None:
        pass  # driven by scene_loop nodes

    # ------------------------------------------------------------------
    # Redis cache helpers (optional, hot-path only)
    # ------------------------------------------------------------------

    @staticmethod
    def _cache_fragment(value: Any) -> str:
        """Convert a cache-key component into a short, Redis-safe fragment."""
        text = str(value or "").strip()
        if not text:
            return "none"
        safe = text.replace(" ", "_").replace(":", "_").replace("/", "_")
        if len(safe) <= 48 and safe.replace("_", "").replace("-", "").isalnum():
            return safe.lower()
        return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]

    def _cache_key(self, *parts: Any) -> str:
        return ":".join(["solo_play", *[self._cache_fragment(part) for part in parts]])

    def _ttl(self, *, short: bool = False) -> int:
        base = max(5, int(settings.redis_solo_play_ttl_seconds or 15))
        return base if short else max(int(settings.redis_cache_ttl_seconds or 30), base * 4)

    def _cache_get_json(self, key: str) -> Any | None:
        try:
            from monitor_data.db.redis import get_redis_client

            return get_redis_client().get_json(key)
        except Exception as exc:
            logger.debug("Redis cache get failed for %s: %s", key, exc)
            return None

    def _cache_set_json(self, key: str, value: Any, *, ttl: int | None = None) -> None:
        try:
            from monitor_data.db.redis import get_redis_client

            get_redis_client().set_json(key, value, ttl=ttl)
        except Exception as exc:
            logger.debug("Redis cache set failed for %s: %s", key, exc)

    @staticmethod
    def _trim_query(query: str, *, max_chars: int) -> str:
        """Trim query text to a bounded size while preserving word boundaries when possible."""
        text = (query or "").strip()
        if len(text) <= max_chars:
            return text
        clipped = text[:max_chars].rsplit(" ", 1)[0].strip()
        return clipped or text[:max_chars].strip()

    @classmethod
    def _append_terms_with_budget(
        cls,
        query: str,
        terms: list[str],
        *,
        max_terms: int,
        max_chars: int,
    ) -> str:
        """Append de-duplicated enrichment terms while respecting query-size budgets."""
        result = cls._trim_query(query, max_chars=max_chars)
        if not terms or max_terms <= 0:
            return result

        appended = 0
        seen: set[str] = set()
        for raw_term in terms:
            term = str(raw_term or "").strip()
            if not term:
                continue
            key = term.lower()
            if key in seen:
                continue
            seen.add(key)

            # Skip if term already appears in query.
            if key in result.lower():
                continue

            candidate = f"{result} {term}".strip()
            if len(candidate) > max_chars:
                break
            result = candidate
            appended += 1
            if appended >= max_terms:
                break

        return result

    # ------------------------------------------------------------------
    # Primary entry points
    # ------------------------------------------------------------------

    async def assemble(
        self,
        scene_id: UUID,
        story_id: UUID,
        player_action: str | None = None,
        character_name: str = "Player",
        character_tags: str = "",
        universe_id: str | None = None,
        system_id: str | None = None,
        system_source_type: str | None = None,
        system_source_id: str | None = None,
        pack_id: str | None = None,
        actor_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Assemble full scene context (entities + memories + recent turns + game system).

        Called by scene_loop.load_context() at the start of each scene.

        Returns:
            {
                "entities":    [...],
                "memories":    [...],
                "turns":       [...],
                "game_system": {...},  # compact game system rules/stats for narrator & resolver
                "summary":     str,   # only if player_action is provided
                "actor":       {...}, # optional actor details (Gap 1)
            }
        """
        cache_key = self._cache_key(
            "assemble",
            scene_id,
            story_id,
            universe_id or "default",
            system_id or "default",
            system_source_type or "direct",
            system_source_id or pack_id or "default",
            player_action or "",
            json.dumps(actor_context or {}, sort_keys=True, default=str),
        )
        cached = self._cache_get_json(cache_key)
        if isinstance(cached, dict):
            return cached

        t_embed = time.perf_counter()
        entities, turns, game_system, plot_threads = await asyncio.gather(
            self._fetch_entities(scene_id),
            self._fetch_recent_turns(scene_id),
            self._fetch_game_system(
                universe_id,
                system_id,
                system_source_type=system_source_type,
                system_source_id=system_source_id,
                pack_id=pack_id,
            ),
            self._fetch_plot_threads(story_id),
        )
        source_profile = await self._fetch_runtime_profile(
            system_name=game_system.get("name") if isinstance(game_system, dict) else None,
        )
        memory_query = expand_query_with_profile(player_action or "", player_action or "", source_profile)

        actor_id: UUID | None = None
        actor_id_str: str | None = None
        if actor_context and actor_context.get("id"):
            actor_id_str = str(actor_context["id"])
            with contextlib.suppress(ValueError, TypeError):
                actor_id = UUID(actor_id_str)

        memories = await self._fetch_memories(
            scene_id, story_id, memory_query, entity_id=actor_id, universe_id=universe_id
        )
        logger.info("SCENE_SPAN embed=%.0fms", (time.perf_counter() - t_embed) * 1000)

        matched_lore: list[str] = []
        profile_context = build_profile_context(source_profile)
        lorebook_before: list[str] = []
        lorebook_after: list[str] = []
        lorebook_depth: list[str] = []

        if player_action and actor_id_str:
            try:
                # Build scan history from recent turns (speaker: content if available).
                history: list[str] = []
                for turn in turns:
                    speaker = turn.get("speaker") or turn.get("name") or ""
                    text = turn.get("content") or turn.get("text") or turn.get("message") or ""
                    if speaker and text:
                        history.append(f"{speaker}: {text}")
                    elif text:
                        history.append(text)

                character_ids = [actor_id_str]
                if universe_id:
                    character_ids.append(f"universe:{universe_id}")

                scan_config = await self.call_tool(
                    "mongodb_get_scan_config", {"character_id": actor_id_str}
                )
                if not isinstance(scan_config, dict):
                    scan_config = {}

                lore_result = await self.call_tool(
                    "mongodb_scan_lorebook",
                    {
                        "character_ids": character_ids,
                        "text": player_action,
                        "history": history,
                        "config": scan_config,
                        "turn_index": len(turns),
                        "increment_triggers": True,
                    },
                )
                if isinstance(lore_result, dict):
                    lorebook_before = lore_result.get("before", []) or []
                    lorebook_after = lore_result.get("after", []) or []
                    lorebook_depth = lore_result.get("depth", []) or []
                    matched_lore = lorebook_before + lorebook_after + lorebook_depth
                elif isinstance(lore_result, list):
                    matched_lore = lore_result

                if lorebook_before:
                    profile_context = (
                        "RELEVANT LOREBOOK ENTRIES:\n"
                        + "\n".join(lorebook_before)
                        + "\n\n"
                        + profile_context
                    )
                if lorebook_after:
                    profile_context += "\n\nRELEVANT LOREBOOK ENTRIES:\n" + "\n".join(lorebook_after)
                if lorebook_depth:
                    profile_context += "\n\nLOREBOOK (@DEPTH):\n" + "\n".join(lorebook_depth)
            except Exception as e:
                logger.warning(f"Failed to inject lorebook entries: {e}")

        result: dict[str, Any] = {
            "entities": entities,
            "memories": memories,
            "turns": turns,
            "game_system": game_system,
            "source_profile": source_profile,
            "plot_threads": plot_threads,
            "lorebook_entries": matched_lore,
        }

        if actor_context:
            result["actor"] = actor_context

        if player_action:
            # P-14: Perform Spatial Filter/Zoom
            # 1. Identify the 'active' location (the one the player is likely in)
            active_location = None
            for e in entities:  # type: ignore[misc]
                if e.get("entity_type") == "location" and "current" in e.get("state_tags", []):
                    active_location = e
                    break

            if active_location:
                # 2. Filter entities to those at the same scale or direct parents
                current_scale = active_location.get("properties", {}).get("spatial_scale", "local")
                filtered_entities = []
                for e in entities:  # type: ignore[misc]
                    e_scale = e.get("properties", {}).get("spatial_scale")
                    # Always include the active location and its parent
                    if e.get("id") == active_location.get("id"):
                        filtered_entities.append(e)
                        continue
                    # Match scale
                    if e_scale == current_scale:
                        filtered_entities.append(e)
                entities = filtered_entities

            result["summary"] = await self._summarise_context(
                player_action=player_action,
                entities=entities,
                memories=memories,
                snippets=[],
                profile_context=profile_context,
                plot_threads=plot_threads,
            )

        self._cache_set_json(cache_key, result, ttl=self._ttl(short=True))
        return result

    async def retrieve_turn_context(
        self,
        scene_id: UUID,
        story_id: UUID,
        player_action: str,
        character_name: str = "Player",
        character_tags: str = "",
        detail_level: str = "full",
        universe_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Retrieve and rank context specifically relevant to a single player action.

        Called for supplementary turn-level context retrieval.

        Returns:
            {
                "entities": [...filtered by relevance],
                "memories": [...filtered by relevance],
                "snippets": [...],
                "summary":  str,
            }
        """
        cache_key = self._cache_key(
            "turn_context",
            scene_id,
            story_id,
            universe_id or "all",
            detail_level,
            character_name,
            character_tags,
            player_action,
        )
        cached = self._cache_get_json(cache_key)
        if isinstance(cached, dict):
            return cached

        scene_summary = await self._build_scene_summary(scene_id)

        # Step 1: Formulate retrieval queries using DSPy
        queries = self._query_formulator(
            player_action=player_action,
            scene_summary=scene_summary,
            character_name=character_name,
            character_tags=character_tags,
        )

        # Step 2: Pull the best available runtime profile and expand the queries.
        game_system = await self._fetch_game_system(universe_id=None, system_id=None)
        source_profile = await self._fetch_runtime_profile(
            system_name=game_system.get("name") if isinstance(game_system, dict) else None,
        )
        source_scope = derive_source_scope(player_action, source_profile)
        expanded_memory_query = expand_query_with_profile(
            queries.memory_query,
            player_action,
            source_profile,
        )
        expanded_memory_query = append_scope_terms_to_query(expanded_memory_query, source_scope)
        expanded_memory_query = self._trim_query(expanded_memory_query, max_chars=280)
        dialogue_intent = is_dialogue_action(player_action)

        if detail_level == "memory_only":
            conversation_turns: list[dict[str, Any]] = []
            ranked_turns: list[dict[str, Any]] = []
            ranked_windows: list[dict[str, Any]] = []
            if dialogue_intent:
                conversation_turns = await self._fetch_recent_conversation_turns(
                    scene_id=scene_id,
                    story_id=story_id,
                    limit=14,
                )
                ranked_turns = rank_conversation_turns(
                    conversation_turns,
                    player_action=player_action,
                    limit=6,
                )
                windows = build_dialogue_turn_windows(conversation_turns, window_size=3, max_windows=8)
                ranked_windows = rank_dialogue_windows(
                    windows,
                    player_action=player_action,
                    limit=4,
                )

                dialogue_focus_terms = compose_dialogue_focus_terms(
                    ranked_turns,
                    ranked_windows,
                    limit=6,
                )
                expanded_memory_query = self._append_terms_with_budget(
                    expanded_memory_query,
                    dialogue_focus_terms,
                    max_terms=5,
                    max_chars=280,
                )

            memories = await self._search_memories(
                expanded_memory_query,
                story_id=story_id,
                universe_id=universe_id,
            )

            if dialogue_intent:
                memories = [
                    *conversation_turns_to_memory_items(ranked_turns),
                    *dialogue_windows_to_memory_items(ranked_windows),
                    *memories,
                ]
            result = {
                "memories": memories,
                "source_profile": source_profile,
                "source_scope": source_scope,
            }
            if conversation_turns:
                result["conversation_turns"] = conversation_turns
            self._cache_set_json(cache_key, result, ttl=self._ttl(short=True))
            return result

        expanded_snippet_query = expand_query_with_profile(
            queries.snippet_query,
            player_action,
            source_profile,
        )
        expanded_snippet_query = append_scope_terms_to_query(expanded_snippet_query, source_scope)
        expanded_snippet_query = self._trim_query(expanded_snippet_query, max_chars=320)

        # Step 3: Retrieval
        entities, memories = await asyncio.gather(
            self._fetch_entities(scene_id),
            self._search_memories(expanded_memory_query, story_id=story_id, universe_id=universe_id),
        )

        conversation_turns = []
        ranked_dialogue_turns: list[dict[str, Any]] = []
        if dialogue_intent:
            conversation_turns = await self._fetch_recent_conversation_turns(
                scene_id=scene_id,
                story_id=story_id,
                limit=14,
            )
            ranked_dialogue_turns = rank_conversation_turns(
                conversation_turns,
                player_action=player_action,
                limit=6,
            )
            dialogue_windows = build_dialogue_turn_windows(
                conversation_turns,
                window_size=3,
                max_windows=8,
            )
            ranked_dialogue_windows = rank_dialogue_windows(
                dialogue_windows,
                player_action=player_action,
                preferred_speakers=[str(entity.get("name")) for entity in entities if entity.get("name")],
                limit=4,
            )
            memories = [
                *conversation_turns_to_memory_items(ranked_dialogue_turns),
                *dialogue_windows_to_memory_items(ranked_dialogue_windows),
                *memories,
            ]
            dialogue_focus_terms = compose_dialogue_focus_terms(
                ranked_dialogue_turns,
                ranked_dialogue_windows,
                limit=8,
            )
            if dialogue_focus_terms:
                expanded_snippet_query = self._append_terms_with_budget(
                    expanded_snippet_query,
                    dialogue_focus_terms,
                    max_terms=8,
                    max_chars=320,
                )

        traversal_mask = build_traversal_mask(
            player_action=player_action,
            source_scope=source_scope,
            seed_entity_ids=[str(entity.get("id") or "") for entity in entities],
        )
        traversal_candidates = await self._collect_traversal_candidates(
            entities=entities,
            traversal_mask=traversal_mask,
        )
        traversal_terms = collect_traversal_query_terms(traversal_candidates, limit=8)
        if traversal_terms:
            expanded_snippet_query = self._append_terms_with_budget(
                expanded_snippet_query,
                traversal_terms,
                max_terms=6,
                max_chars=320,
            )

        entity_names = [e.get("name", "") for e in entities if e.get("name")]
        snippets = await self._search_snippets_for_entities(
            expanded_snippet_query,
            entity_names,
            source_profile=source_profile,
            player_action=player_action,
            source_scope=source_scope,
            universe_id=universe_id,
        )

        # Step 4: Summarise for injection into downstream prompts.
        summary = await self._summarise_context(
            player_action=player_action,
            entities=entities,
            memories=memories,
            snippets=snippets,
            profile_context=build_profile_context(source_profile),
        )

        result = {
            "entities": entities,
            "memories": memories,
            "snippets": snippets,
            "summary": summary,
            "source_profile": source_profile,
            "source_scope": source_scope,
        }
        if conversation_turns:
            result["conversation_turns"] = conversation_turns
        if traversal_candidates:
            result["traversal_mask"] = traversal_mask
            result["traversal_candidates"] = traversal_candidates[:6]
        self._cache_set_json(cache_key, result, ttl=self._ttl(short=True))
        return result

    # ------------------------------------------------------------------
    # Private fetch helpers
    # ------------------------------------------------------------------

    async def _fetch_entities(self, scene_id: UUID) -> list[dict[str, Any]]:
        """Fetch entities present in the current scene from Neo4j via MCP."""
        cache_key = self._cache_key("scene_entities", scene_id)
        cached = self._cache_get_json(cache_key)
        if isinstance(cached, list):
            return cached

        raw = await self.call_tool(
            "neo4j_get_entities_by_scene",
            {"scene_id": str(scene_id)},
        )
        if not raw:
            self._cache_set_json(cache_key, [], ttl=self._ttl(short=True))
            return []
        try:
            entities = json.loads(raw) if isinstance(raw, str) else raw
        except (json.JSONDecodeError, TypeError):
            logger.warning("context_assembly: JSON parse failed for entities, returning []", exc_info=True)
            return []
        self._cache_set_json(cache_key, entities, ttl=self._ttl(short=True))
        return cast(list[dict[str, Any]], entities)

    async def _fetch_memories(
        self,
        scene_id: UUID,
        story_id: UUID,
        query: str,
        entity_id: UUID | None = None,
        universe_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Search character memories from Qdrant.

        G2 FIX: Added optional entity_id filter so memories can be scoped to a
        specific character (or all characters when entity_id is None).
        """
        if not query:
            return []
        cache_key = self._cache_key(
            "story_memories",
            story_id,
            query,
            (entity_id.hex if entity_id else "all") + "_" + (universe_id or "all"),
        )
        cached = self._cache_get_json(cache_key)
        if isinstance(cached, list):
            return cast(list[dict[str, Any]], cached)

        # G2: Build filter with optional entity_id scope
        filter_dict: dict[str, Any] = {"story_id": str(story_id)}
        if entity_id:
            filter_dict["entity_id"] = str(entity_id)
        if universe_id:
            filter_dict["universe_id"] = str(universe_id)

        raw = await self.call_tool(
            "qdrant_search",
            {
                "collection": "memories",
                "query_text": query,
                "limit": 10,
                "filter": filter_dict,
            },
        )
        if not raw:
            self._cache_set_json(cache_key, [], ttl=self._ttl(short=True))
            return []
        try:
            memories = json.loads(raw) if isinstance(raw, str) else raw
        except (json.JSONDecodeError, TypeError):
            logger.warning("context_assembly: JSON parse failed for memories, returning []", exc_info=True)
            return []
        self._cache_set_json(cache_key, memories, ttl=self._ttl(short=True))
        return cast(list[dict[str, Any]], memories)

    async def _fetch_recent_turns(self, scene_id: UUID) -> list[dict[str, Any]]:
        """Fetch recent turn history from MongoDB via MCP."""
        cache_key = self._cache_key("scene_turns", scene_id)
        cached = self._cache_get_json(cache_key)
        if isinstance(cached, list):
            return cast(list[dict[str, Any]], cached)

        raw = await self.call_tool(
            "mongodb_get_recent_turns",
            {"scene_id": str(scene_id), "limit": 10},
        )
        if not raw:
            self._cache_set_json(cache_key, [], ttl=max(5, self._ttl(short=True) // 2))
            return []
        try:
            turns = json.loads(raw) if isinstance(raw, str) else raw
        except (json.JSONDecodeError, TypeError):
            logger.warning("context_assembly: JSON parse failed for turns, returning []", exc_info=True)
            return []
        self._cache_set_json(cache_key, turns, ttl=max(5, self._ttl(short=True) // 2))
        return cast(list[dict[str, Any]], turns)

    async def _fetch_plot_threads(self, story_id: UUID) -> list[dict[str, Any]]:
        """Fetch active plot threads for the story from Neo4j via MCP."""
        cache_key = self._cache_key("story_plot_threads", story_id)
        cached = self._cache_get_json(cache_key)
        if isinstance(cached, list):
            return cast(list[dict[str, Any]], cached)

        try:
            # We avoid importing PlotThreadFilter here to prevent circular/hanging imports
            # from monitor_data.schemas.story_outlines which sometimes triggers DB init.
            # The tool expects a dict with story_id, status, limit.
            params = {
                "story_id": str(story_id),
                "status": "active",
                "limit": 10,
            }
            raw = await self.call_tool(
                "neo4j_list_plot_threads",
                {"params": params},
            )
            if not raw:
                self._cache_set_json(cache_key, [], ttl=self._ttl(short=True))
                return []

            payload = json.loads(raw) if isinstance(raw, str) else raw
            threads = payload.get("threads", []) if isinstance(payload, dict) else []

            self._cache_set_json(cache_key, threads, ttl=self._ttl(short=True))
            return cast(list[dict[str, Any]], threads)
        except Exception as exc:
            logger.debug("_fetch_plot_threads failed: %s", exc)
            return []

    async def _search_memories(
        self,
        query: str,
        *,
        story_id: UUID | None = None,
        universe_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Semantic search over Qdrant memories collection."""
        cache_key = self._cache_key("memory_search", story_id or "global", universe_id or "all", query)
        cached = self._cache_get_json(cache_key)
        if isinstance(cached, list):
            return cast(list[dict[str, Any]], cached)

        params: dict[str, Any] = {
            "collection": "memories",
            "query_text": query,
            "limit": 8,
        }
        filter_dict: dict[str, Any] = {}
        if story_id is not None:
            filter_dict["story_id"] = str(story_id)
        if universe_id is not None:
            filter_dict["universe_id"] = str(universe_id)
        if filter_dict:
            params["filter"] = filter_dict

        raw = await self.call_tool(
            "qdrant_search",
            params,
        )
        if not raw:
            self._cache_set_json(cache_key, [], ttl=self._ttl(short=True))
            return []
        try:
            memories = json.loads(raw) if isinstance(raw, str) else raw
        except (json.JSONDecodeError, TypeError):
            logger.warning(
                "context_assembly: JSON parse failed for memories (qdrant), returning []",
                exc_info=True,
            )
            return []
        self._cache_set_json(cache_key, memories, ttl=self._ttl(short=True))
        return cast(list[dict[str, Any]], memories)

    async def _fetch_recent_conversation_turns(
        self,
        *,
        scene_id: UUID,
        story_id: UUID,
        limit: int = 12,
    ) -> list[dict[str, Any]]:
        """Fetch recent flattened conversation turns from MongoDB via MCP."""
        cache_key = self._cache_key("conversation_turns", scene_id, story_id, limit)
        cached = self._cache_get_json(cache_key)
        if isinstance(cached, list):
            return cached

        raw = await self.call_tool(
            "mongodb_get_recent_conversation_turns",
            {
                "scene_id": str(scene_id),
                "story_id": str(story_id),
                "limit": int(limit),
            },
        )
        if not raw:
            self._cache_set_json(cache_key, [], ttl=max(5, self._ttl(short=True) // 2))
            return []
        try:
            turns = json.loads(raw) if isinstance(raw, str) else raw
        except (json.JSONDecodeError, TypeError):
            turns = []

        if not isinstance(turns, list):
            turns = []
        self._cache_set_json(cache_key, turns, ttl=max(5, self._ttl(short=True) // 2))
        return turns

    async def _search_snippets(
        self,
        query: str,
        *,
        query_vector: list[float] | None = None,
        universe_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Semantic search over Qdrant snippets (ingested docs) collection.

        Scoped to ``universe_id`` when provided so a session never retrieves a
        different world's ingested source material (the snippets payload carries
        an indexed ``universe_id``).
        """
        if not query and not query_vector:
            return []
        cache_key = self._cache_key("snippet_search", query, universe_id or "all")
        cached = self._cache_get_json(cache_key)
        if isinstance(cached, list):
            return cached

        params: dict[str, Any] = {"collection": "snippets", "limit": 6}
        if universe_id:
            params["filter"] = {"universe_id": str(universe_id)}
        if query_vector:
            params["query_vector"] = query_vector
        else:
            params["query_text"] = query

        raw = await self.call_tool(
            "qdrant_search",
            params,
        )
        if not raw:
            self._cache_set_json(cache_key, [], ttl=self._ttl(short=True))
            return []
        try:
            snippets = json.loads(raw) if isinstance(raw, str) else raw
        except (json.JSONDecodeError, TypeError):
            logger.warning("context_assembly: JSON parse failed for snippets, returning []", exc_info=True)
            return []
        self._cache_set_json(cache_key, snippets, ttl=self._ttl(short=True))
        return cast(list[dict[str, Any]], snippets)

    async def _search_snippets_for_entities(
        self,
        query: str,
        entity_names: list[str],
        *,
        source_profile: dict[str, Any] | None = None,
        player_action: str = "",
        source_scope: dict[str, Any] | None = None,
        universe_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Hybrid snippet retrieval: semantic vector search pre-filtered by entity names.

        For each entity name, issues a MatchText-filtered Qdrant search so that
        only chunks mentioning the entity are ranked by the vector score.  Results
        from all entity searches are merged, deduplicated by chunk_id, then merged
        with a plain semantic search for any context not captured by name-matching.

        Returns at most 12 snippets, ranked by relevance score.
        """
        cache_key = self._cache_key(
            "entity_snippets",
            query,
            ",".join(sorted(name for name in entity_names if name)),
            player_action,
            json.dumps(source_profile or {}, sort_keys=True, default=str),
            json.dumps(source_scope or {}, sort_keys=True, default=str),
            universe_id or "all",
        )
        cached = self._cache_get_json(cache_key)
        if isinstance(cached, list):
            return cached
        if not query.strip():
            self._cache_set_json(cache_key, [], ttl=self._ttl(short=True))
            return []

        seen_ids: set[str] = set()
        scored: list[tuple[float, dict[str, Any]]] = []
        from monitor_data.retrieval import default_retrieval_service

        query_vector = await default_retrieval_service().embed_query(query)

        # Per-entity keyword-filtered searches (MatchText pre-filter + vector ranking)
        entity_names = entity_names[:8]  # cap to avoid too many round-trips
        keyword_responses = await asyncio.gather(
            *[
                self.call_tool(
                    "qdrant_search",
                    {
                        "collection": "snippets",
                        "query_vector": query_vector,
                        "top_k": 4,
                        "keyword_filter": name,
                        **({"filter": {"universe_id": str(universe_id)}} if universe_id else {}),
                    },
                )
                for name in entity_names
            ],
            return_exceptions=True,
        )
        for raw in keyword_responses:
            if isinstance(raw, BaseException) or not raw:
                continue
            try:
                results = json.loads(raw) if isinstance(raw, str) else raw
            except (json.JSONDecodeError, TypeError):
                logger.warning(
                    "context_assembly: JSON parse failed for keyword search result, skipping",
                    exc_info=True,
                )
                continue
            for item in results:
                cid = item.get("chunk_id") or item.get("id") or str(item)
                if cid not in seen_ids:
                    seen_ids.add(cid)
                    scored.append((item.get("score", 0.0), item))

        # Plain semantic search as safety net for context not mention-matched
        plain = await self._search_snippets(query, query_vector=query_vector, universe_id=universe_id)
        for item in plain:
            cid = item.get("chunk_id") or item.get("id") or str(item)
            if cid not in seen_ids:
                seen_ids.add(cid)
                scored.append((item.get("score", 0.0), item))

        # Re-rank with profile-aware boosts, then return top-12.
        scored.sort(key=lambda t: t[0], reverse=True)
        merged = [item for _, item in scored[:24]]
        ranked = rank_snippets_with_profile(
            merged,
            player_action=player_action or query,
            profile=source_profile,
        )
        ranked = rank_snippets_with_source_scope(
            ranked,
            scope=source_scope or {},
            player_action=player_action or query,
        )
        top_ranked = ranked[:12]
        self._cache_set_json(cache_key, top_ranked, ttl=self._ttl(short=True))
        return top_ranked

    async def _collect_traversal_candidates(
        self,
        *,
        entities: list[dict[str, Any]],
        traversal_mask: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Collect bounded relationship/path candidates for query-aware traversal."""
        seed_entity_ids = [str(entity.get("id") or "") for entity in entities if str(entity.get("id") or "").strip()][
            :5
        ]
        if not seed_entity_ids:
            return []

        preferred_rel_types = traversal_mask.get("preferred_rel_types") or []
        candidates: list[dict[str, Any]] = []

        # First, pull bounded ranked-path signals (up to hop_limit) and project them as
        # traversal candidates so query enrichment can include multi-hop context.
        try:
            ranked_paths_raw = await self.call_tool(
                "neo4j_find_ranked_paths",
                {
                    "seed_entity_ids": seed_entity_ids,
                    "rel_types": preferred_rel_types,
                    "hop_limit": int(traversal_mask.get("hop_limit", 2) or 2),
                    "limit": 12,
                },
            )
        except Exception:
            ranked_paths_raw = None

        ranked_paths: list[dict[str, Any]] = []
        if ranked_paths_raw is not None:
            try:
                payload = json.loads(ranked_paths_raw) if isinstance(ranked_paths_raw, str) else ranked_paths_raw
            except (json.JSONDecodeError, TypeError):
                payload = []
            if isinstance(payload, list):
                ranked_paths = [row for row in payload if isinstance(row, dict)]

        for path in ranked_paths:
            counterpart_id = str(path.get("target_entity_id") or "").strip()
            if not counterpart_id:
                continue

            rel_chain = [str(rel).upper() for rel in (path.get("rel_chain") or []) if str(rel).strip()]
            rel_type = rel_chain[0] if rel_chain else "RELATED_TO"
            hop_count = int(path.get("hop_count") or 1)

            # Multi-hop paths are highly relevant context; apply a bounded boost.
            path_score = 0.85 + max(0.0, (2 - min(hop_count, 2)) * 0.1)

            candidates.append(
                {
                    "anchor_entity_id": str(path.get("seed_entity_id") or "").strip(),
                    "anchor_name": str(path.get("seed_name") or "").strip(),
                    "counterpart_entity_id": counterpart_id,
                    "counterpart_name": path.get("target_name"),
                    "rel_type": rel_type,
                    "rel_chain": rel_chain,
                    "hop_count": hop_count,
                    "score": path_score,
                    "source": "ranked_path",
                }
            )

        for entity in entities[:5]:
            anchor_id = str(entity.get("id") or "").strip()
            if not anchor_id:
                continue
            anchor_name = str(entity.get("name") or "").strip()

            relationships: list[dict[str, Any]] = []
            try:
                raw = await self.call_tool(
                    "neo4j_get_entity_neighborhood",
                    {
                        "entity_id": anchor_id,
                        "direction": "both",
                        "limit": 12,
                        "rel_types": preferred_rel_types,
                    },
                )
            except Exception:
                raw = None

            if raw is not None:
                try:
                    payload = json.loads(raw) if isinstance(raw, str) else raw
                except (json.JSONDecodeError, TypeError):
                    payload = {}
                if isinstance(payload, list):
                    relationships = payload
                elif isinstance(payload, dict):
                    relationships = payload.get("relationships", [])

            if not relationships:
                try:
                    fallback_raw = await self.call_tool(
                        "neo4j_list_relationships",
                        {
                            "params": {
                                "entity_id": anchor_id,
                                "direction": "both",
                                "limit": 12,
                            }
                        },
                    )
                except Exception:
                    fallback_raw = None

                if fallback_raw is not None:
                    try:
                        fallback_payload = json.loads(fallback_raw) if isinstance(fallback_raw, str) else fallback_raw
                    except (json.JSONDecodeError, TypeError):
                        fallback_payload = {}
                    if isinstance(fallback_payload, list):
                        relationships = fallback_payload
                    elif isinstance(fallback_payload, dict):
                        relationships = fallback_payload.get("relationships", [])

            for relationship in relationships:
                if not isinstance(relationship, dict):
                    continue
                score = score_candidate_relationship(
                    relationship,
                    preferred_rel_types=preferred_rel_types,
                )
                relationship_counterpart_id = get_counterpart_entity_id(
                    relationship,
                    anchor_entity_id=anchor_id,
                )
                if not relationship_counterpart_id:
                    continue

                candidates.append(
                    {
                        "anchor_entity_id": anchor_id,
                        "anchor_name": anchor_name,
                        "counterpart_entity_id": relationship_counterpart_id,
                        "rel_type": relationship.get("rel_type"),
                        "score": score,
                        "source": "neighborhood",
                    }
                )

        if not candidates:
            return []

        candidates.sort(key=lambda item: float(item.get("score", 0.0)), reverse=True)
        deduped: list[dict[str, Any]] = []
        seen_keys: set[tuple[str, str]] = set()
        for candidate in candidates:
            key = (
                str(candidate.get("counterpart_entity_id") or "").strip(),
                str(candidate.get("rel_type") or "").upper().strip(),
            )
            if not key[0] or key in seen_keys:
                continue
            seen_keys.add(key)
            deduped.append(candidate)
            if len(deduped) >= 10:
                break

        top_candidates = deduped[:10]

        for candidate in top_candidates:
            counterpart_id = str(candidate.get("counterpart_entity_id") or "").strip()
            if not counterpart_id:
                continue
            try:
                entity_raw = await self.call_tool(
                    "neo4j_get_entity",
                    {"entity_id": str(counterpart_id)},
                )
            except Exception:
                entity_raw = None

            counterpart: dict[str, Any] = {}
            if isinstance(entity_raw, str):
                try:
                    counterpart = json.loads(entity_raw)
                except json.JSONDecodeError:
                    counterpart = {}
            elif isinstance(entity_raw, dict):
                counterpart = entity_raw

            if counterpart.get("name"):
                candidate["counterpart_name"] = counterpart.get("name")

        return top_candidates

    async def _fetch_game_system(
        self,
        universe_id: str | None,
        system_id: str | None = None,
        *,
        system_source_type: str | None = None,
        system_source_id: str | None = None,
        pack_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Load the raw game system document from MongoDB for the current universe.

        If a session selected a specific ``system_id``, prefer that document so
        the live scene loop uses the intended ruleset instead of whichever system
        happened to be updated most recently.

        Returns the full document so that callers (Narrator, Resolver) can
        construct a ``GameSystemRuntime`` from it and drive logic from the schema.
        Returns {} on any failure so the loop always continues.
        """
        cache_key = self._cache_key(
            "game_system",
            system_id or "unbound",
            system_source_type or "direct",
            system_source_id or pack_id or "default",
            universe_id or "global",
        )
        cached = self._cache_get_json(cache_key)
        if isinstance(cached, dict):
            return cached

        try:

            def _load_game_system() -> dict[str, Any]:
                from monitor_data.db.mongodb import get_mongodb_client
                from monitor_data.tools.mongodb_tools import mongodb_get_knowledge_pack

                resolved_system_id = system_id
                resolved_source_type = system_source_type
                resolved_source_id = system_source_id or pack_id

                if not resolved_source_type and pack_id:
                    resolved_source_type = "pack_embedded"

                if not resolved_system_id and resolved_source_type == "generic_library" and resolved_source_id:
                    resolved_system_id = str(resolved_source_id)

                if resolved_source_type == "pack_embedded" and resolved_source_id:
                    try:
                        pack = mongodb_get_knowledge_pack(UUID(str(resolved_source_id)))
                    except (TypeError, ValueError):
                        pack = None
                    if pack is not None:
                        embedded = getattr(pack, "game_system_data", None)
                        if embedded is not None:
                            return cast(dict[str, Any], embedded.model_dump(mode="json"))
                        if not resolved_system_id and getattr(pack, "game_system_id", None):
                            resolved_system_id = str(pack.game_system_id)

                if not resolved_system_id:
                    return {}

                mdb = get_mongodb_client()
                col = mdb.get_collection("game_systems")
                return col.find_one({"system_id": resolved_system_id}, projection={"_id": 0}) or {}

            doc = await asyncio.to_thread(_load_game_system)
            if doc:
                self._cache_set_json(cache_key, doc, ttl=self._ttl())
                return doc

            if not system_id and not system_source_id and not pack_id:
                logger.debug(
                    "_fetch_game_system: no explicit binding resolved for universe=%s; continuing without a rules document",
                    universe_id,
                )
            else:
                logger.warning(
                    "_fetch_game_system: no rules document found for system_id='%s'; continuing without a rules document",
                    system_id,
                )
            self._cache_set_json(cache_key, {}, ttl=self._ttl(short=True))
            return {}
        except Exception as exc:
            logger.debug("_fetch_game_system failed: %s", exc)
            return {}

    async def _fetch_runtime_profile(self, system_name: str | None = None) -> dict[str, Any]:
        """Fetch the freshest embedded source profile that matches the active system when possible."""
        cache_key = self._cache_key("runtime_profile", system_name or "default")
        cached = self._cache_get_json(cache_key)
        if isinstance(cached, dict):
            return cached

        try:
            from monitor_data.schemas.knowledge_packs import (
                KnowledgePackFilter,
                KnowledgePackStatus,
            )
            from monitor_data.tools.mongodb_tools import mongodb_list_knowledge_packs

            def _load_candidates() -> list[Any]:
                candidates = []
                if system_name:
                    primary = mongodb_list_knowledge_packs(
                        KnowledgePackFilter(
                            system_name=system_name,
                            status=KnowledgePackStatus.READY,
                            limit=10,
                        )
                    )
                    candidates = [
                        pack
                        for pack in primary.packs
                        if getattr(pack, "source_profile_data", None) is not None
                        or getattr(pack, "source_mindscape", None) is not None
                    ]

                if not candidates:
                    fallback = mongodb_list_knowledge_packs(
                        KnowledgePackFilter(
                            status=KnowledgePackStatus.READY,
                            limit=20,
                        )
                    )
                    candidates = [
                        pack
                        for pack in fallback.packs
                        if getattr(pack, "source_profile_data", None) is not None
                        or getattr(pack, "source_mindscape", None) is not None
                    ]
                    if system_name:
                        narrowed = [
                            pack
                            for pack in candidates
                            if (pack.system_name or "") == system_name or system_name in (pack.tags or [])
                        ]
                        if narrowed:
                            candidates = narrowed
                return candidates

            candidates = await asyncio.to_thread(_load_candidates)

            if not candidates:
                self._cache_set_json(cache_key, {}, ttl=self._ttl())
                return {}

            selected = candidates[0]
            normalized = normalize_source_profile(getattr(selected, "source_profile_data", None))
            if not normalized:
                mindscape = getattr(selected, "source_mindscape", None)
                if mindscape is not None:
                    if hasattr(mindscape, "model_dump"):
                        mindscape = mindscape.model_dump(mode="json")
                    elif not isinstance(mindscape, dict):
                        try:
                            mindscape = vars(mindscape)
                        except TypeError:
                            mindscape = {}
                    if isinstance(mindscape, dict):
                        confidence = float(mindscape.get("confidence", 0.0) or 0.0)
                        normalized = normalize_source_profile(
                            {
                                "system_name": mindscape.get("system_name")
                                or (getattr(selected, "system_name", None) or system_name),
                                "genre_tone": list(mindscape.get("themes", []) or []),
                                "taxonomy_containers": list(mindscape.get("taxonomy_hints", []) or []),
                                "canon_signal_terms": list(mindscape.get("taxonomy_hints", []) or []),
                                "coverage_summary": mindscape.get("summary", "") or "",
                                "confidence_by_field": {
                                    "system_name": confidence,
                                    "genre_tone": confidence,
                                    "taxonomy_containers": confidence,
                                    "canon_signal_terms": confidence,
                                },
                            }
                        )
            self._cache_set_json(cache_key, normalized, ttl=self._ttl())
            return normalized
        except Exception as exc:
            logger.debug("_fetch_runtime_profile failed: %s", exc)
            return {}

    async def _build_scene_summary(self, scene_id: UUID) -> str:
        """Fetch a brief scene summary from MongoDB for query formulation."""
        cache_key = self._cache_key("scene_summary", scene_id)
        cached = self._cache_get_json(cache_key)
        if isinstance(cached, str) and cached:
            return cached

        raw = await self.call_tool(
            "mongodb_get_scene_summary",
            {"scene_id": str(scene_id)},
        )
        summary = raw or "Unknown scene"
        self._cache_set_json(cache_key, summary, ttl=max(5, self._ttl(short=True) // 2))
        return summary

    async def _summarise_context(
        self,
        player_action: str,
        entities: list[dict[str, Any]],
        memories: list[dict[str, Any]],
        snippets: list[dict[str, Any]],
        profile_context: str = "",
        plot_threads: list[dict[str, Any]] | None = None,
    ) -> str:
        """Deterministic context ranking and compression — no LLM call.

        Replaces the former DSPy ContextAssemblyModule (ChainOfThought) with
        a deterministic pipeline that:
        1. Scores each context item by term-overlap with the player action.
        2. Ranks by score (descending).
        3. Formats items into a structured text summary.
        4. Truncates to the token budget (STANDARD.summary_budget ≈ 1024).

        This eliminates one LLM call per turn (~2-5s saved) with no loss in
        context quality — the LLM summarizer was mostly deduplicating and
        reordering, which scoring does faster and cheaper.
        """
        action_terms = _extract_terms(player_action)
        profile_terms = _extract_terms(profile_context) if profile_context else set()

        # Build scored items from all sources.
        scored_items: list[tuple[float, str]] = []

        # Always include active plot threads with high importance
        if plot_threads:
            for thread in plot_threads:
                title = thread.get("title", "")
                if not title:
                    continue
                score = _score_item(title, action_terms, profile_terms)
                # Boost plot threads significantly so the GM stays on theme
                score += 1.5
                scored_items.append((score, f"[Plot Thread] {title} (Status: {thread.get('status', 'active')})"))

        for entity in entities[:20]:
            text = _entity_to_text(entity)
            if not text:
                continue
            score = _score_item(text, action_terms, profile_terms)
            score += entity.get("importance", 0.0) * 0.2  # boost important entities
            scored_items.append((score, f"[Entity] {text}"))

        for memory in memories[:10]:
            text = memory.get("text", "") or memory.get("content", "") or ""
            if not text:
                continue
            score = _score_item(text, action_terms, profile_terms)
            vec_score = float(memory.get("score", 0.0))
            score += vec_score * 0.3  # boost by vector similarity
            scored_items.append((score, f"[Memory] {text[:300]}"))

        for snippet in snippets[:6]:
            text = snippet.get("text", "") or snippet.get("content", "") or ""
            if not text:
                continue
            score = _score_item(text, action_terms, profile_terms)
            vec_score = float(snippet.get("score", 0.0))
            score += vec_score * 0.3
            scored_items.append((score, f"[Snippet] {text[:400]}"))

        # Sort by relevance, descending.
        scored_items.sort(key=lambda t: t[0], reverse=True)

        # Build summary within token budget.
        max_tokens = self._token_budget.summary_budget
        lines: list[str] = []
        current_tokens = 0

        for _score, text in scored_items:
            item_tokens = count_tokens(text)
            if current_tokens + item_tokens > max_tokens:
                # Try to fit a truncated version.
                remaining = max_tokens - current_tokens
                if remaining < 30:
                    break
                truncated = truncate_to_tokens(text, remaining)
                lines.append(truncated)
                break
            lines.append(text)
            current_tokens += item_tokens

        if not lines:
            return "No relevant context found."

        header = f"Context for action: {player_action[:120]}"
        return f"{header}\n" + "\n".join(lines)

    # ------------------------------------------------------------------
    # G3: Auto-summarization trigger
    # ------------------------------------------------------------------

    async def check_and_compress_if_needed(
        self,
        assembled_context: dict[str, Any],
        player_action: str,
    ) -> dict[str, Any]:
        """
        G3: If the assembled context exceeds the token budget, compress memories.

        Called from SceneLoop.load_context after assemble() returns.
        Checks context size against available budget and, if exceeded,
        re-summarises memories to fit within summary_budget.

        Returns the context unchanged if within budget.
        """
        context_tokens = count_tokens(json.dumps(assembled_context, default=str))
        available = self._token_budget.available_for_context(prompt_tokens=context_tokens)

        # If we have headroom, nothing to do
        if available > 0:
            return assembled_context

        # Compress: re-run _summarise_context on the memories list
        memories = assembled_context.get("memories", [])
        if not memories:
            return assembled_context

        summarised = await self._summarise_context(
            player_action=player_action,
            entities=assembled_context.get("entities", []),
            memories=memories,
            snippets=assembled_context.get("snippets", []),
            profile_context=assembled_context.get("source_profile", ""),
        )

        assembled_context["memories"] = [{"text": summarised, "is_summary": True}]
        assembled_context["_compressed"] = True
        return assembled_context
