import logging
import re
from typing import Any
from uuid import UUID

from monitor_agents.base import BaseAgent
from monitor_agents.resource_engine import ResourceEngine

logger = logging.getLogger(__name__)


class WorldRulesAgent(BaseAgent):
    """
    Agent responsible for consistency checks and event/resource resolution
    within the world rules (Fase Alto).
    """

    def __init__(self, agent_id: str, model: str | None = None) -> None:
        super().__init__(agent_type="world_rules", agent_id=agent_id, model=model)

    async def run(self, *args: Any, **kwargs: Any) -> Any:
        pass

    async def check_consistency(
        self,
        narrative_text: str | None,
        established_facts: list[str],
        turn_context: dict[str, Any] | None,
        source_profile: dict[str, Any] | None,
        scene_id: UUID,
    ) -> dict[str, Any]:
        """
        Lightweight consistency check against established facts.
        """
        if not narrative_text:
            return {}

        violations: list[dict[str, Any]] = []

        established_names: dict[str, str] = {}
        for fact in established_facts:
            if fact.startswith("Named entity mentioned: "):
                name = fact[len("Named entity mentioned: ") :].strip()
                key = name.split()[0].lower() if name else ""
                if key:
                    established_names[key] = name

        ship_name_pattern = re.compile(
            r"(?:hull reads|(?:ship|vessel)(?:'s name)?\s+is(?:\s+called|\s+named)?|"
            r"(?:ship|vessel)\s+(?:called|named))\s+\*?([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\*?",
            re.IGNORECASE,
        )
        for match in ship_name_pattern.finditer(narrative_text):
            found_name = match.group(1).strip()
            for key, established_name in established_names.items():
                if (
                    found_name.lower() != established_name.lower()
                    and found_name.lower() != key
                    and established_name.lower() not in found_name.lower()
                    and found_name.lower() not in established_name.lower()
                ):
                    violations.append(
                        {
                            "type": "name_drift",
                            "expected": established_name,
                            "found": found_name,
                            "severity": "high",
                            "message": (
                                f"Narrator used '{found_name}' but established name is "
                                f"'{established_name}'. This may cause player confusion."
                            ),
                        }
                    )

        expected_genre = ""
        if turn_context and isinstance(turn_context, dict):
            expected_genre = turn_context.get("genre", "").lower()
        elif source_profile:
            expected_genre = source_profile.get("genre", "").lower() if isinstance(source_profile, dict) else ""

        if expected_genre:
            medieval_terms = [
                "tavern",
                "hearth",
                "corkboard",
                "ale",
                "mead",
                "innkeeper",
                "sword",
                "spell",
                "mage",
                "dragon",
                "knight",
                "castle",
            ]
            sci_fi_terms = [
                "airlock",
                "corridor",
                "datapad",
                "dataslate",
                "station",
                "void",
                "hull",
                "bulkhead",
                "recycled air",
                "salvage",
            ]
            text_lower = narrative_text.lower()

            if expected_genre == "sci-fi":
                for term in medieval_terms:
                    if term in text_lower:
                        has_sci = any(t in text_lower for t in sci_fi_terms)
                        if not has_sci:
                            violations.append(
                                {
                                    "type": "genre_drift",
                                    "expected": "sci-fi",
                                    "found": f"medieval term '{term}'",
                                    "severity": "high",
                                    "message": (
                                        f"Narrator used medieval term '{term}' in a sci-fi setting. "
                                        f"This indicates genre drift."
                                    ),
                                }
                            )
                            break

        for fact in established_facts:
            if fact.startswith("State change: "):
                entity_state = fact[len("State change: ") :]
                if "sealed" in entity_state and "opens" in narrative_text.lower():
                    pass

        if not violations:
            return {}

        logger.warning(
            "Consistency check found %d violation(s) in scene %s: %s",
            len(violations),
            scene_id,
            violations,
        )
        return {"consistency_violations": violations}

    async def check_events(
        self,
        game_context: dict[str, Any],
        working_state: dict[str, Any],
        user_input: str | None,
        turns_count: int,
        scene_complete: bool,
        resolution: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """
        FASE ALTO (Item 1): ResourceEngine — detect spends, apply earns, fire thresholds.
        """
        if not game_context or not working_state:
            return {
                "pending_spends": [],
                "threshold_events": [],
                "injected_narrative_events": [],
                "resource_deltas": [],
            }

        engine = ResourceEngine(game_context, working_state)

        pending_spends = [
            {
                "resource_key": s.resource_key,
                "resource_name": s.resource_name,
                "amount": s.amount,
                "intent": s.intent,
                "can_afford": s.can_afford,
            }
            for s in engine.detect_spend(user_input or "")
        ]

        scene_ctx = {
            "turns_count": turns_count,
            "scene_ending": scene_complete,
        }
        earned = engine.apply_earn(resolution or {}, scene_context=scene_ctx)
        economy = engine.apply_action_economy(user_input or "", resolution or {})
        resource_deltas = [
            {
                "resource_key": d.resource_key,
                "resource_name": d.resource_name,
                "delta": d.delta,
                "source": d.source,
                "reason": d.reason,
            }
            for d in (earned + economy)
        ]

        threshold_events = [
            {
                "resource_key": e.resource_key,
                "resource_name": e.resource_name,
                "threshold_value": e.threshold_value,
                "direction": e.direction,
                "effect": e.effect,
                "new_value": e.new_value,
            }
            for e in engine.check_thresholds()
        ]

        injected_events: list[dict[str, Any]] = [
            {
                "trigger": "threshold",
                "resource_key": te["resource_key"],
                "narrative": f"[{te['resource_name']} @ {te['threshold_value']}] {te['effect']}",
                "effects": [],
            }
            for te in threshold_events
        ]

        return {
            "pending_spends": pending_spends,
            "threshold_events": threshold_events,
            "injected_narrative_events": injected_events,
            "resource_deltas": resource_deltas,
        }
