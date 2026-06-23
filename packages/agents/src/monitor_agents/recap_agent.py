"""
Recap Agent — generates "The Story So Far" summaries.

LAYER: 2 (agents)
Authority: MongoDB (scenes, story_outlines), Neo4j (facts)
"""

import json
import logging
from typing import Optional
from uuid import UUID

from monitor_agents.base import BaseAgent
from monitor_agents.prompts.recap import RecapModule
from monitor_agents.utils.db_readers import (
    mongodb_get_story_outline,
    mongodb_list_scenes,
    neo4j_list_facts,
    run_sync_read,
)
from monitor_data.schemas.facts import FactFilter
from monitor_data.schemas.llm_config import ModelRole
from monitor_data.schemas.scenes import SceneFilter
from monitor_data.schemas.base import SceneStatus

logger = logging.getLogger(__name__)


class RecapAgent(BaseAgent):
    """
    Agent responsible for generating narrative recaps.
    """

    def __init__(self, model: Optional[str] = None) -> None:
        super().__init__(
            agent_type="RecapAgent",
            agent_id="recap-001",
            model=model,
        )
        self.module = RecapModule()

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
        outline_result = await run_sync_read(mongodb_get_story_outline, story_id)
        outline_json = json.dumps(outline_result, indent=2, default=str) if outline_result else "{}"

        # 2. Fetch completed scenes for this story
        scene_filter = SceneFilter(
            story_id=story_id,
            status=SceneStatus.COMPLETED,
            limit=20,
        )
        scenes_result = await run_sync_read(mongodb_list_scenes, scene_filter)
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
        facts_result = await run_sync_read(neo4j_list_facts, fact_filter)
        facts_list = (
            [f.get("statement", "") for f in facts_result if isinstance(f, list) for f in f]
            if isinstance(facts_result, list)
            else []
        )
        facts_json = json.dumps(facts_list, indent=2, default=str)

        # 4. Run LLM
        prediction = self.module.forward(
            story_outline=outline_json,
            scene_summaries=scenes_json,
            significant_facts=facts_json,
            tone_context=tone_context,
            role=ModelRole.STANDARD,
        )

        return prediction.recap_markdown

    async def run(self) -> None:
        """Implemented for BaseAgent compliance; usually called via generate_recap."""
        pass
