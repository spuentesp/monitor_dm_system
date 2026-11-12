"""
CaptureInsightAgent — per-entry insights for the Session Recorder.

LAYER: 2 (agents)
IMPORTS FROM: monitor_data (Layer 1), monitor_agents.prompts
CALLED BY: UI backend

Use Cases: CF-1 (Session Recorder capture loop), P1.2 (capture insights)

This agent:
1. Fetches canonical entity names and open plot threads from Neo4j
2. Runs the CaptureEntryModule (DSPy, ModelRole.LIGHT) on a single entry
3. Returns participants, locations, and candidate facts for inline display

Candidate facts are returned for inline display and promoted by the caller
into pending, story-scoped CF-8 review proposals when capture context is
available. The agent itself remains read-only.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any
from uuid import UUID

import structlog
from pydantic import BaseModel, Field

from monitor_agents.base import BaseAgent

log = structlog.get_logger()


# =============================================================================
# RESPONSE SCHEMAS
# =============================================================================


class CaptureInsight(BaseModel):
    """Inline insights for one Session Recorder entry."""

    participants: list[str] = Field(default_factory=list, description="Entities acting or referenced in the entry")
    locations: list[str] = Field(default_factory=list, description="Places grounded in the entry text")
    candidate_facts: list[str] = Field(default_factory=list, description="World-state claims implied by the entry")
    advances_thread: str = Field(default="", description="Open thread this entry advances, or empty string")


def _proposal_result(result: Any, proposal_id: str) -> dict[str, Any]:
    """Normalize an MCP proposal tool result into a dict.

    ``BaseAgent.call_tool`` returns tool failures as the raw string
    ``"Error executing tool: ..."`` — surface those as ValueError so the
    router can map them to 404/409 responses.
    """
    if isinstance(result, dict):
        return result
    if isinstance(result, str) and result.startswith("Error executing tool:"):
        raise ValueError(result.removeprefix("Error executing tool:").strip())
    raise ValueError(f"Proposal {proposal_id} could not be updated")


# =============================================================================
# CAPTURE INSIGHT AGENT
# =============================================================================


class CaptureInsightAgent(BaseAgent):
    """
    Analyzes a single capture entry for participants, locations, and
    candidate facts (CF-1, P1.2).

    Advisory only: an LLM failure yields an empty insight so logging is
    never blocked.
    """

    def __init__(
        self,
        agent_type: str = "CaptureInsightAgent",
        agent_id: str | None = None,
        model: str | None = None,
    ) -> None:
        super().__init__(
            agent_type=agent_type,
            agent_id=agent_id or "capture-insight-agent",
            model=model,
        )

    async def analyze_entry(self, universe_id: UUID, entry_text: str) -> CaptureInsight:
        """
        Analyze one Session Recorder entry for inline insights.

        Args:
            universe_id: The universe the capture session belongs to
            entry_text: The logged entry text

        Returns:
            CaptureInsight with participants, locations, candidate facts,
            and the open thread the entry advances (if any). Empty on LLM
            failure — never raises for analysis problems.
        """
        # 1. Fetch canonical entity names from Neo4j
        entities_result = await self.call_tool(
            "neo4j_list_entities",
            {"filters": {"universe_id": str(universe_id), "limit": 50}},
        )
        entities = self._parse_result(entities_result, "entities", [])
        known_entities = [str(e.get("name")) for e in entities if e.get("name")]

        # 2. Fetch open plot threads from Neo4j
        threads_result = await self.call_tool(
            "neo4j_list_plot_threads",
            {"params": {"status": "active"}},
        )
        threads = self._parse_result(threads_result, "threads", [])
        open_threads = [str(t.get("title", "Untitled")) for t in threads]

        # 3. Run the DSPy module off the event loop (LIGHT role — per-entry volume)
        from monitor_data.schemas.llm_config import ModelRole

        from monitor_agents.dspy_runtime import dspy_context_for
        from monitor_agents.ingestion.session_ingest import CaptureEntryModule

        module = CaptureEntryModule()

        def _predict() -> Any:
            with dspy_context_for("capture_insights", ModelRole.LIGHT):
                return module.forward(
                    entry_text=entry_text,
                    known_entities=known_entities,
                    open_threads=open_threads,
                )

        try:
            prediction = await asyncio.to_thread(_predict)
            return CaptureInsight(
                participants=list(prediction.participants or []),
                locations=list(prediction.locations or []),
                candidate_facts=list(prediction.candidate_facts or []),
                advances_thread=str(prediction.advances_thread or ""),
            )
        except Exception as exc:  # noqa: BLE001  # reason: boundary logs and degrades gracefully (in _predict)
            log.warning(
                "capture_insights_llm_failed",
                universe_id=str(universe_id),
                error=str(exc),
            )
            return CaptureInsight()

    # ------------------------------------------------------------------
    # Proposal correction (G03 — CF-1 amendment)
    # ------------------------------------------------------------------

    async def retract_proposal(
        self,
        proposal_id: str,
        reason: str = "struck at the table",
        entry_id: str | None = None,
    ) -> dict[str, Any]:
        """Retract a pending candidate proposal (pending → rejected).

        The reason lands in the proposal's decision metadata so CF-8 shows
        why it disappeared. ``entry_id`` ties the retract to the struck
        session entry that caused it.
        """
        args: dict[str, Any] = {"proposal_id": proposal_id, "reason": reason}
        if entry_id is not None:
            args["entry_id"] = entry_id
        result = await self.call_tool("mongodb_retract_proposed_change", args)
        return _proposal_result(result, proposal_id)

    async def restore_proposal(
        self,
        proposal_id: str,
        reason: str = "struck at the table",
    ) -> dict[str, Any]:
        """Undo a GM retract: flip the matching rejected proposal back to pending."""
        result = await self.call_tool(
            "mongodb_restore_retracted_proposal",
            {"proposal_id": proposal_id, "reason": reason},
        )
        return _proposal_result(result, proposal_id)

    # ------------------------------------------------------------------
    # BaseAgent compliance
    # ------------------------------------------------------------------

    async def run(self) -> None:
        """Implemented for BaseAgent compliance; usually called via analyze_entry."""
        pass

    # ------------------------------------------------------------------
    # HELPERS
    # ------------------------------------------------------------------

    def _parse_result(self, result: Any, key: str, default: Any) -> Any:
        """Parse MCP tool result, handling JSON strings and dicts."""
        if isinstance(result, str):
            try:
                result = json.loads(result)
            except (json.JSONDecodeError, TypeError):
                return default
        if isinstance(result, dict):
            return result.get(key, default)
        if isinstance(result, list):
            return result
        return default
