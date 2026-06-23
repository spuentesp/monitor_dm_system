"""
Oracle Agent implementation.

LAYER: 2 (agents)
Purpose: Resolve world-truth questions with structured probability.
"""

import logging
from enum import Enum
from typing import Any, Dict
from monitor_data.utils.dice import roll_dice
from monitor_agents.base import BaseAgent

logger = logging.getLogger(__name__)


class Likelihood(Enum):
    CERTAIN = "certain"  # 100% (No roll)
    NEARLY_CERTAIN = "nearly_certain"  # 90% (2+)
    VERY_LIKELY = "very_likely"  # 80% (5+)
    LIKELY = "likely"  # 65% (8+)
    FIFTY_FIFTY = "50_50"  # 50% (11+)
    UNLIKELY = "unlikely"  # 35% (14+)
    VERY_UNLIKELY = "very_unlikely"  # 20% (17+)
    NEARLY_IMPOSSIBLE = "nearly_impossible"  # 10% (19+)
    IMPOSSIBLE = "impossible"  # 0% (No roll)


class OracleOutcome(Enum):
    YES_AND = "yes_and"  # Exceptional success
    YES = "yes"  # Standard success
    YES_BUT = "yes_but"  # Success with complication
    NO_BUT = "no_but"  # Failure with silver lining
    NO = "no"  # Standard failure
    NO_AND = "no_and"  # Exceptional failure


class Oracle(BaseAgent):
    """
    Agent responsible for answering questions about unknown world states.
    Uses a probability-based 'Oracle' mechanic inspired by Mythic/Ironsworn.
    """

    def __init__(self, agent_id: str = "oracle-1") -> None:
        super().__init__(agent_type="Oracle", agent_id=agent_id)

    def resolve_question(
        self,
        question: str,
        likelihood: Likelihood = Likelihood.FIFTY_FIFTY,
        tension_score: float = 0.5,
    ) -> Dict[str, Any]:
        """
        Resolve a binary question using the Oracle mechanic.

        Tension score (0.0 - 1.0) skews the result: higher tension makes
        a 'Yes' outcome harder (increases the DC).
        """
        # 1. Map Likelihood to DC (Target to beat on 1d20)
        dc_map = {
            Likelihood.NEARLY_CERTAIN: 2,
            Likelihood.VERY_LIKELY: 5,
            Likelihood.LIKELY: 8,
            Likelihood.FIFTY_FIFTY: 11,
            Likelihood.UNLIKELY: 14,
            Likelihood.VERY_UNLIKELY: 17,
            Likelihood.NEARLY_IMPOSSIBLE: 19,
        }

        if likelihood == Likelihood.CERTAIN:
            return self._format_result(question, likelihood, OracleOutcome.YES, 20, 0)
        if likelihood == Likelihood.IMPOSSIBLE:
            return self._format_result(question, likelihood, OracleOutcome.NO, 1, 0)

        base_dc = dc_map.get(likelihood, 11)

        # Tension skew: shift DC by -2 to +2 based on tension (0.5 is neutral)
        tension_skew = int((tension_score - 0.5) * 4)
        dc = max(2, min(19, base_dc + tension_skew))

        # 2. Roll d20
        roll = roll_dice("1d20")
        total = roll.total

        # 3. Determine Outcome
        if total == 20:
            outcome = OracleOutcome.YES_AND
        elif total == 1:
            outcome = OracleOutcome.NO_AND
        elif total >= dc:
            outcome = OracleOutcome.YES_BUT if total == dc and dc > 2 else OracleOutcome.YES
        else:
            outcome = OracleOutcome.NO_BUT if total == dc - 1 and dc < 20 else OracleOutcome.NO

        return self._format_result(question, likelihood, outcome, total, dc)

    def _format_result(
        self, question: str, likelihood: Likelihood, outcome: OracleOutcome, roll: int, dc: int
    ) -> Dict[str, Any]:
        return {
            "question": question,
            "likelihood": likelihood.value,
            "outcome": outcome.value,
            "roll": roll,
            "dc": dc,
            "is_yes": outcome in [OracleOutcome.YES, OracleOutcome.YES_AND, OracleOutcome.YES_BUT],
            "is_exceptional": outcome in [OracleOutcome.YES_AND, OracleOutcome.NO_AND],
            "has_complication": outcome in [OracleOutcome.YES_BUT, OracleOutcome.NO_BUT],
        }

    async def run(self) -> None:
        pass
