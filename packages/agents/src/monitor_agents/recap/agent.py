"""
Recap Agent — generates "The Story So Far" summaries.

LAYER: 2 (agents)
Authority: MongoDB (scenes, story_outlines), Neo4j (facts)
"""

import json
import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from monitor_data.schemas.arc_recaps import ArcRecap, ArcRecapCreate, ArcRecapDetail
from monitor_data.schemas.base import ProposalStatus, SceneStatus
from monitor_data.schemas.facts import FactFilter
from monitor_data.schemas.llm_config import ModelRole
from monitor_data.schemas.proposed_changes import ProposedChangeFilter
from monitor_data.schemas.scenes import SceneFilter
from monitor_data.schemas.story_outlines import PlotThreadFilter

from monitor_agents.base import BaseAgent
from monitor_agents.recap.recap import ArcRecapModule, RecapModule
from monitor_agents.utils.db_readers import (
    mongodb_get_story_outline,
    mongodb_list_proposed_changes,
    mongodb_list_scenes,
    mongodb_save_arc_recap,
    neo4j_list_facts,
    neo4j_list_plot_threads,
    run_sync_read,
)

logger = logging.getLogger(__name__)

# Scene recaps are condensed into arc beats chunk by chunk so a long campaign
# stays within the model's context window (map-reduce; precedent:
# ContextAssembly.get_full_scene_history chunking).
ARC_RECAP_CHUNK_SIZE = 8


def _change_label(content: dict[str, Any], change_type: str) -> str:
    """Best-effort human-readable label for an accepted proposed change."""
    for key in ("description", "name", "title", "text", "summary", "content"):
        value = content.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return change_type.replace("_", " ")


class RecapAgent(BaseAgent):
    """
    Agent responsible for generating narrative recaps.
    """

    def __init__(self, model: str | None = None) -> None:
        super().__init__(
            agent_type="RecapAgent",
            agent_id="recap-001",
            model=model,
        )
        self.module = RecapModule()
        self.arc_module = ArcRecapModule()

    async def generate_recap(
        self,
        story_id: UUID,
        universe_id: UUID,
        tone_context: str = "Compelling, dramatic narrative summary.",
    ) -> str:
        """
        Generate a "The Story So Far" recap for a story.
        """
        # 1. Fetch story outline (sync read — wrap in thread)
        outline_result = await run_sync_read(mongodb_get_story_outline, story_id)  # type: ignore[var-annotated]
        outline_json = json.dumps(outline_result, indent=2, default=str) if outline_result else "{}"

        # 2. Fetch completed scenes for this story
        scene_filter = SceneFilter(
            story_id=story_id,
            status=SceneStatus.COMPLETED,
            limit=20,
        )
        scenes_result = await run_sync_read(mongodb_list_scenes, scene_filter)  # type: ignore[var-annotated]
        scene_summaries = []
        if isinstance(scenes_result, dict) and "scenes" in scenes_result:
            for s in scenes_result["scenes"]:
                summary = s.get("summary", "").strip()
                if not summary:
                    summary = f"Scene: {s.get('title', 'Untitled')}"
                scene_summaries.append(summary)
        scenes_json = json.dumps(scene_summaries, indent=2, default=str)

        # 3. Fetch significant facts from Neo4j
        fact_filter = FactFilter(
            universe_id=universe_id,
            min_magnitude=4,
            limit=15,
        )
        facts_result = await run_sync_read(neo4j_list_facts, fact_filter)  # type: ignore[var-annotated]
        facts_list = (
            [f.get("statement", "") for f in facts_result if isinstance(f, list) for f in f]
            if isinstance(facts_result, list)
            else []
        )
        facts_json = json.dumps(facts_list, indent=2, default=str)

        # 4. The story's ledger: what happened in each finished scene.
        ledger_entries = await self._read_ledger(story_id)
        ledger_json = json.dumps(
            [
                {
                    "scene_index": entry.get("scene_index"),
                    "summary": entry.get("summary"),
                    "start_time": entry.get("start_time"),
                    "end_time": entry.get("end_time"),
                    "open_questions": entry.get("open_questions"),
                }
                for entry in ledger_entries
            ],
            indent=2,
            default=str,
        )

        # Nothing to recap: an LLM will still produce fluent "the story hasn't
        # started yet" prose from empty inputs rather than erroring, which
        # calling code can't distinguish from a real recap by length alone.
        # Signal emptiness explicitly instead of paying for/masking it with a
        # generated non-recap. Every bootstrapped story gets a placeholder
        # outline (generic theme/premise/template, empty beats) the moment
        # it's created, so outline_result alone is truthy even when nothing
        # has actually happened yet -- `beats` is the field real play fills
        # in (see narrator.py / story_loop.py), so it's the meaningful signal.
        has_outline_content = bool((outline_result or {}).get("beats"))
        if not has_outline_content and not scene_summaries and not facts_list and not ledger_entries:
            return ""

        # 5. Run LLM
        prediction = self.module.forward(
            story_outline=outline_json,
            scene_summaries=scenes_json,
            significant_facts=facts_json,
            story_ledger=ledger_json,
            tone_context=tone_context,
            role=ModelRole.STANDARD,
        )

        return prediction.recap_markdown  # type: ignore[no-any-return]

    async def generate_arc_recap(
        self,
        story_id: UUID,
        universe_id: UUID,
        detail: ArcRecapDetail | str = ArcRecapDetail.STANDARD,
        persist: bool = True,
    ) -> ArcRecap | None:
        """
        Generate a campaign-level (story-arc) recap across ALL scenes of a story (CF-12).

        Hierarchical map-reduce: per-scene summaries are condensed into arc beats
        chunk by chunk, then the beats are synthesized into one campaign summary
        covering major arcs, party journey, faction shifts, and resolved vs. open
        threads. Only accepted proposals count as canon deltas.

        The result is persisted as the story's single arc_recap document (upsert),
        stored with `generated_at` and a scene watermark. Returns None when the
        story has nothing to recap yet (no scenes, beats, facts, or accepted
        changes) — no LLM call and no persistence in that case.
        """
        try:
            detail_level = ArcRecapDetail(detail)
        except ValueError:
            valid = [d.value for d in ArcRecapDetail]
            raise ValueError(f"detail must be one of {valid}, got {detail!r}") from None

        # 1. Story outline
        outline_result = await run_sync_read(mongodb_get_story_outline, story_id)  # type: ignore[var-annotated]
        outline_json = json.dumps(outline_result, indent=2, default=str) if outline_result else "{}"

        # 2. ALL scenes of the story, oldest first (the recap covers the whole campaign)
        scenes_result = await run_sync_read(  # type: ignore[var-annotated]
            mongodb_list_scenes,
            SceneFilter(story_id=story_id, limit=1000, sort_by="created_at", sort_order="asc"),
        )
        scenes: list[dict[str, Any]] = (
            scenes_result.get("scenes", []) if isinstance(scenes_result, dict) else []
        )
        scene_entries = [
            {
                "scene_id": s.get("scene_id"),
                "title": s.get("title", "Untitled"),
                "status": s.get("status", ""),
                "narrative_order": s.get("narrative_order"),
                "summary": (s.get("summary") or "").strip() or f"Scene: {s.get('title', 'Untitled')}",
            }
            for s in scenes
        ]

        # 3. Significant canon facts (Neo4j only holds accepted canon)
        facts_result = await run_sync_read(  # type: ignore[var-annotated]
            neo4j_list_facts,
            FactFilter(universe_id=universe_id, min_magnitude=4, limit=50),
        )
        facts_list: list[str] = []
        if isinstance(facts_result, list):
            for item in facts_result:
                if isinstance(item, dict):
                    facts_list.append(item.get("statement", ""))
                elif isinstance(item, list):
                    facts_list.extend(f.get("statement", "") for f in item if isinstance(f, dict))
        facts_json = json.dumps(facts_list, indent=2, default=str)

        # 4. Accepted proposed changes only — pending/rejected never count as canon
        accepted_result = await run_sync_read(  # type: ignore[var-annotated]
            mongodb_list_proposed_changes,
            ProposedChangeFilter(story_id=story_id, status=ProposalStatus.ACCEPTED, limit=200),
        )
        accepted_changes = (
            [
                {
                    "change_type": p.get("change_type", ""),
                    "label": _change_label(p.get("content") or {}, str(p.get("change_type", ""))),
                }
                for p in accepted_result.get("proposed_changes", [])
            ]
            if isinstance(accepted_result, dict)
            else []
        )
        accepted_json = json.dumps(accepted_changes, indent=2, default=str)

        # 5. Plot threads (open and resolved)
        threads_result = await run_sync_read(  # type: ignore[var-annotated]
            neo4j_list_plot_threads,
            PlotThreadFilter(story_id=story_id, limit=100),
        )
        thread_entries = (
            [
                {
                    "title": t.get("title", "Untitled"),
                    "status": t.get("status", ""),
                    "thread_type": t.get("thread_type", ""),
                }
                for t in threads_result.get("threads", [])
            ]
            if isinstance(threads_result, dict)
            else []
        )
        threads_json = json.dumps(thread_entries, indent=2, default=str)

        # Nothing to recap: signal emptiness instead of paying for an LLM call
        # that would produce fluent filler (same contract as generate_recap).
        has_outline_content = bool((outline_result or {}).get("beats"))
        if not has_outline_content and not scene_entries and not facts_list and not accepted_changes:
            return None

        # 6. Map: condense each chunk of scene recaps into arc beats.
        chunk_beats: list[str] = []
        for start in range(0, len(scene_entries), ARC_RECAP_CHUNK_SIZE):
            chunk = scene_entries[start : start + ARC_RECAP_CHUNK_SIZE]
            beats_prediction = self.arc_module.summarize_chunk(
                story_outline=outline_json,
                scene_recaps=json.dumps(chunk, indent=2, default=str),
                detail=detail_level.value,
                role=ModelRole.STANDARD,
            )
            chunk_beats.append(beats_prediction.arc_beats)

        # 7. Reduce: synthesize the campaign-level recap from the chunk beats.
        campaign_prediction = self.arc_module.synthesize_campaign(
            story_outline=outline_json,
            arc_beats=json.dumps(chunk_beats, indent=2, default=str),
            significant_facts=facts_json,
            accepted_changes=accepted_json,
            plot_threads=threads_json,
            detail=detail_level.value,
            role=ModelRole.STANDARD,
        )
        recap_markdown = campaign_prediction.recap_markdown

        # 8. Scene watermark: how far into the campaign this recap reaches.
        watermark = max((str(s.get("updated_at") or "") for s in scenes), default="")
        create = ArcRecapCreate(
            story_id=story_id,
            universe_id=universe_id,
            recap_markdown=recap_markdown,
            detail=detail_level,
            scene_count=len(scene_entries),
            scenes_watermark=watermark,
            last_scene_id=UUID(scene_entries[-1]["scene_id"]) if scene_entries and scene_entries[-1].get("scene_id") else None,
        )
        if persist:
            return await run_sync_read(mongodb_save_arc_recap, create)

        now = datetime.now(UTC)
        return ArcRecap(
            recap_id=uuid4(),
            generated_at=now,
            updated_at=now,
            **create.model_dump(),
        )

    async def run(self) -> None:
        """Implemented for BaseAgent compliance; usually called via generate_recap."""
        pass

    async def _read_ledger(self, story_id: UUID) -> list[dict[str, Any]]:
        """Read the story's ledger, oldest first.

        A ledger that cannot be read leaves the recap with the rest of the
        story's history.
        """
        from monitor_data.tools.mongodb_tools.stories import mongodb_list_story_ledger_entries

        try:
            entries = await run_sync_read(mongodb_list_story_ledger_entries, story_id)  # type: ignore[var-annotated]
        except Exception as exc:  # noqa: BLE001  # reason: boundary logs and degrades gracefully (in _read_ledger)
            logger.warning("Could not read the ledger of story %s: %s", story_id, exc)
            return []
        if not isinstance(entries, list):
            return []
        return [entry.model_dump(mode="json") if hasattr(entry, "model_dump") else dict(entry) for entry in entries]
