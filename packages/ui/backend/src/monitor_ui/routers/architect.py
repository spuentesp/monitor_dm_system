"""
World Architect router (F2-1 wave 1).

Currently exposes the formal coverage report: a structured, per-dimension
view of what a universe contains and where its gaps are, computed read-only
by the WorldArchitect agent (FORGE_EXPANSION.md §2). The wave-2 workbench
frontend consumes this endpoint; the existing prose coverage_summary /
known_open_questions / priority_gaps flow in the chat router is untouched.
"""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from monitor_data.schemas.coverage import CoverageThresholds, WorldCoverage
from monitor_data.tools.neo4j_tools import neo4j_get_universe

router = APIRouter()


@router.get("/architect/{universe_id}/coverage", response_model=WorldCoverage)
async def get_world_coverage(
    universe_id: UUID,
    require_mechanics: bool = Query(
        default=False,
        description="Treat game mechanics as required (mechanical play intent)",
    ),
    require_random_tables: bool = Query(
        default=False,
        description="Treat random tables as required (procedural generation intent)",
    ),
) -> WorldCoverage:
    """Return the structured WorldCoverage report for a universe.

    Status semantics: identity + >=1 axiom is the floor; mechanics/tables only
    count toward the rollup when the corresponding query flag marks them
    applicable.
    """
    try:
        from monitor_agents.world_architect.agent import WorldArchitect

        universe = neo4j_get_universe(universe_id)
        if not universe:
            raise HTTPException(404, "Universe not found")

        thresholds = CoverageThresholds(
            require_mechanics=require_mechanics,
            require_random_tables=require_random_tables,
        )
        architect = WorldArchitect()
        return await architect.compute_coverage(universe_id, thresholds=thresholds)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(503, f"Coverage computation failed: {exc}") from exc
