"""
Simulacrum Agent — resolves off-screen world movement and faction agency.

This agent implements the "Simulacrum Council" logic, using multiple DSPy
modules (Opportunist, Realist, Reconciler) to decide how the world
advances between scenes.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any
from uuid import UUID

import dspy
from monitor_data.schemas.llm_config import ModelRole

from monitor_agents.base import BaseAgent
from monitor_agents.dspy_runtime import dspy_context_for
from monitor_agents.simulacrum.simulacrum import (
    CouncilReconcilerSignature,
    OpportunistSimulacrumSignature,
    RealistSimulacrumSignature,
)

logger = logging.getLogger(__name__)


class SimulacrumAgent(BaseAgent):
    """
    Manages the background simulation of the world.
    """

    def __init__(self, agent_id: str = "simulacrum-1") -> None:
        super().__init__(agent_type="Simulacrum", agent_id=agent_id)
        self._opportunist = dspy.ChainOfThought(OpportunistSimulacrumSignature)
        self._realist = dspy.ChainOfThought(RealistSimulacrumSignature)
        self._reconciler = dspy.ChainOfThought(CouncilReconcilerSignature)

    async def run(self) -> None:
        pass

    async def run_world_tick(
        self,
        universe_id: UUID,
        current_time: datetime,
        recent_high_impact_events: list[dict[str, Any]],
        world_tone: str = "dramatic",
    ) -> list[dict[str, Any]]:
        """
        Processes one simulation tick for the entire world.

        Fetches active Agendas and runs the Simulacrum Council to advance them.
        """
        import anyio

        # 1. Fetch active agendas from Neo4j
        agendas = await self.call_tool("neo4j_list_agendas", {"universe_id": str(universe_id), "status": "active"})

        if not agendas:
            logger.info(f"No active agendas found for universe {universe_id}. Simulation skipped.")
            return []

        events_str = json.dumps(recent_high_impact_events, indent=2, default=str)
        time_str = current_time.isoformat()

        def _run_council_sync() -> list[dict[str, Any]]:
            all_proposals: list[dict[str, Any]] = []
            with dspy_context_for("simulacrum", ModelRole.HEAVY):
                # The 'agendas' variable from outer scope is a list of dicts from Neo4j
                for agenda in agendas:
                    agenda_id = agenda.get("id")
                    agenda_title = agenda.get("title", "Unknown Agenda")
                    owner_name = agenda.get("owner_name", "Unknown Faction")

                    # Full context for the AI
                    agenda_context = json.dumps(
                        {
                            "title": agenda_title,
                            "description": agenda.get("description"),
                            "type": agenda.get("agenda_type"),
                            "current_segments": agenda.get("current_segments"),
                            "total_segments": agenda.get("total_segments"),
                        },
                        default=str,
                    )

                    try:
                        # 1. Get Opportunist proposal
                        opp_res = self._opportunist(
                            current_time=time_str,
                            high_impact_events=events_str,
                            faction_name=owner_name,
                            faction_agenda=agenda_context,
                        )

                        # 2. Get Realist proposal
                        real_res = self._realist(
                            current_time=time_str,
                            high_impact_events=events_str,
                            faction_name=owner_name,
                            faction_agenda=agenda_context,
                        )

                        # 3. Reconcile
                        final_res = self._reconciler(
                            opportunist_move=opp_res.proposed_move,
                            realist_move=real_res.proposed_move,
                            world_tone=world_tone,
                        )

                        # 4. Create specialized clock-advance proposal
                        if final_res.clock_tick != 0:
                            all_proposals.append(
                                {
                                    "change_type": "mechanic",
                                    "proposal_type": "update_agenda_clock",
                                    "summary": f"{agenda_title}: {final_res.summary}",
                                    "content": {
                                        "agenda_id": agenda_id,
                                        "agenda_title": agenda_title,
                                        "owner_name": owner_name,
                                        "tick": final_res.clock_tick,
                                        "move_details": final_res.final_decision,
                                        "reasoning": f"Opp: {opp_res.reasoning} | Real: {real_res.reasoning}",
                                    },
                                    "magnitude": 5,
                                    "scope": "regional",
                                }
                            )

                        # Also create a fact if the move has narrative impact
                        if final_res.change_type == "create_fact":
                            all_proposals.append(
                                {
                                    "change_type": "create_fact",
                                    "summary": final_res.summary,
                                    "content": {
                                        "statement": f"Background move by {owner_name}: {final_res.final_decision}",
                                        "confidence": 0.8,
                                        "tags": ["simulacrum", "faction_move"],
                                    },
                                    "magnitude": 3,
                                    "scope": "regional",
                                }
                            )

                    except Exception as exc:
                        logger.error(f"Simulacrum Council failed for agenda {agenda_title}: {exc}")
                        continue

            return all_proposals

        return await anyio.to_thread.run_sync(_run_council_sync)
