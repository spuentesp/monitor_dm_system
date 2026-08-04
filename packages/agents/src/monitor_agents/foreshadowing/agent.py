"""ForeshadowingAgent — proposes plants/payoffs after each narration."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import dspy

from monitor_agents.dspy_runtime import dspy_context_for
from monitor_data.schemas.llm_config import ModelRole


class ForeshadowingSignature(dspy.Signature):  # type: ignore[misc]
    """Propose 0-2 new narrative plants and 0-2 payoffs of existing plants.

    A plant is a small, future-relevant detail introduced this turn.
    A payoff is when an existing plant is honored (resolved, referenced,
    or significantly acknowledged).
    """

    narrative_text: str = dspy.InputField(desc="The narration just produced this turn.")
    player_action: str = dspy.InputField(desc="The player's declared action or dialogue.")
    entity_names: str = dspy.InputField(desc="Comma-separated names of entities present in the scene.")
    plants: str = dspy.OutputField(
        desc='JSON array of new plants: [{"summary": str, "target_turn": int}]. Max 2 items. [] if none.'
    )
    payoffs: str = dspy.OutputField(desc='JSON array of payoffs: [{"summary": str}]. Max 2 items. Empty [] if none.')


class ForeshadowingAgent:
    def __init__(self) -> None:
        self._module = dspy.Predict(ForeshadowingSignature)

    async def propose(
        self,
        *,
        scene_id: UUID,
        story_id: UUID,
        narrative_text: str,
        entities: list[dict[str, Any]],
        player_action: str,
    ) -> dict[str, list[dict[str, Any]]]:
        with dspy_context_for("foreshadowing", ModelRole.LIGHT):
            prediction = self._module(
                narrative_text=narrative_text or "(none)",
                player_action=player_action or "(none)",
                entity_names=", ".join(str(e.get("name") or "") for e in entities if isinstance(e, dict)),
            )
        plants = self._safe_json_list(getattr(prediction, "plants", "[]"))
        payoffs = self._safe_json_list(getattr(prediction, "payoffs", "[]"))
        return {"plants": plants[:2], "payoffs": payoffs[:2]}

    @staticmethod
    def _safe_json_list(raw: str) -> list[dict[str, Any]]:
        try:
            parsed = json.loads(raw)
            return [p for p in parsed if isinstance(p, dict)] if isinstance(parsed, list) else []
        except (json.JSONDecodeError, TypeError):
            return []
