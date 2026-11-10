"""
DSPy Signatures and Modules for Memory Extraction.

LAYER: 2 (agents)
IMPORTS FROM: dspy, monitor_agents

Extracts salient memories from narrative turns to be persisted for character growth.

Phase 4 (Task 6): extraction output is typed. ``MemoryExtractor.forward``
validates every item through ``ExtractedMemory`` and, on a JSON parse
failure, returns no memories instead of the old raw-text fallback that
pasted unparseable LLM prose into the memory store. ``forward_typed``
exposes the parse status (``parse_ok`` / ``error``) so callers can record
the failure through ``RoleplayErrorRecorder`` rather than degrade silently.
"""

import json
import logging
from typing import Any

import dspy
from monitor_data.schemas.llm_config import ModelRole
from pydantic import BaseModel, Field

from monitor_agents.dspy_runtime import dspy_context_for

logger = logging.getLogger(__name__)


# =============================================================================
# TYPED OUTPUT
# =============================================================================


class ExtractedMemory(BaseModel):
    """One extracted memory, typed (Task 6)."""

    text: str = Field(min_length=1, max_length=5000, description="The memory description")
    importance: float = Field(default=5.0, ge=0.0, le=10.0, description="1-10 significance")
    emotional_valence: float = Field(default=0.0, ge=-1.0, le=1.0)


class MemoryExtractionResult(BaseModel):
    """Typed extraction output — what replaced the raw-text fallback."""

    memories: list[ExtractedMemory] = Field(default_factory=list)
    parse_ok: bool = True
    error: str | None = None

    def as_dicts(self) -> list[dict[str, Any]]:
        return [m.model_dump() for m in self.memories]


# =============================================================================
# SIGNATURES
# =============================================================================


class MemoryExtractionSignature(dspy.Signature):  # type: ignore[misc]
    """
    Extract salient character memories from a narrative turn.

    Focus on:
    - Significant emotional shifts
    - Key plot revelations
    - Notable interactions with other characters
    - Accomplishments or failures that define the character's journey
    """

    narrative_text: str = dspy.InputField(desc="The prose of the scene turn")
    resolution: str = dspy.InputField(desc="Mechanic resolution summary")
    actor_name: str = dspy.InputField(desc="Name of the acting character")

    memories: str = dspy.OutputField(
        desc=(
            "JSON list of dictionaries with keys: "
            "'text' (str: the memory description in first-person or third-person), "
            "'importance' (int: 1-10, how significant this is), "
            "'emotional_valence' (float: -1.0 to 1.0, negative to positive feeling)"
        )
    )


# =============================================================================
# MODULES
# =============================================================================


class MemoryExtractor(dspy.Module):  # type: ignore[misc]
    """
    ChainOfThought memory extractor — reasons about what makes a memory salient.
    """

    def __init__(self) -> None:
        super().__init__()
        self.extract = dspy.Predict(MemoryExtractionSignature)

    def forward_typed(
        self,
        narrative_text: str,
        resolution: str,
        actor_name: str,
        role: ModelRole | None = None,
    ) -> MemoryExtractionResult:
        """Extract and validate memories; never returns raw-text fakes.

        On a JSON parse failure the result is ``MemoryExtractionResult(
        memories=[], parse_ok=False, error=...)`` — a typed output the caller
        records, not unparseable prose smuggled into the memory store.
        """
        with dspy_context_for("memory_extraction", role or ModelRole.STANDARD):
            prediction = self.extract(
                narrative_text=narrative_text,
                resolution=resolution,
                actor_name=actor_name,
            )

        raw_memories = prediction.memories
        parsed = self._parse_memories(raw_memories)
        if parsed is None:
            return MemoryExtractionResult(
                memories=[],
                parse_ok=False,
                error=f"unparseable extraction output: {str(raw_memories)[:200]}",
            )
        return MemoryExtractionResult(memories=parsed, parse_ok=True)

    def forward(
        self,
        narrative_text: str,
        resolution: str,
        actor_name: str,
        role: ModelRole | None = None,
    ) -> list[dict[str, Any]]:
        """Dict-list view of :meth:`forward_typed` (legacy callers)."""
        return self.forward_typed(narrative_text, resolution, actor_name, role).as_dicts()

    @staticmethod
    def _parse_memories(raw_memories: Any) -> list[ExtractedMemory] | None:
        """Parse the LLM output into typed memories; None when unparseable."""
        raw = raw_memories if isinstance(raw_memories, str) else json.dumps(raw_memories)
        try:
            # Try to find JSON block if the LLM added prose
            if "```json" in raw:
                raw = raw.split("```json")[1].split("```")[0].strip()
            elif "```" in raw:
                raw = raw.split("```")[1].split("```")[0].strip()

            memories = json.loads(raw)
            if not isinstance(memories, list):
                return None
            typed: list[ExtractedMemory] = []
            for item in memories:
                if not isinstance(item, dict):
                    continue
                text = str(item.get("text") or "").strip()
                if not text:
                    continue
                typed.append(
                    ExtractedMemory.model_validate(
                        {
                            "text": text[:5000],
                            "importance": _coerce_importance(item.get("importance")),
                            "emotional_valence": _coerce_valence(item.get("emotional_valence")),
                        }
                    )
                )
            return typed
        except (json.JSONDecodeError, IndexError, ValueError) as e:
            logger.warning("Failed to parse memories from LLM output: %s", e)
            return None


def _coerce_importance(raw: Any) -> float:
    try:
        value = float(raw if raw is not None else 5)
    except (TypeError, ValueError):
        return 5.0
    return max(0.0, min(10.0, value))


def _coerce_valence(raw: Any) -> float:
    try:
        value = float(raw if raw is not None else 0.0)
    except (TypeError, ValueError):
        return 0.0
    return max(-1.0, min(1.0, value))
