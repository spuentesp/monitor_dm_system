"""
DSPy Signatures and Modules for Memory Extraction.

LAYER: 2 (agents)
IMPORTS FROM: dspy, monitor_agents

Extracts salient memories from narrative turns to be persisted for character growth.
"""

import json
import logging
from typing import Any, Dict, List, Optional

import dspy
from monitor_agents.dspy_runtime import dspy_context_for
from monitor_data.schemas.llm_config import ModelRole

logger = logging.getLogger(__name__)

# =============================================================================
# SIGNATURES
# =============================================================================


class MemoryExtractionSignature(dspy.Signature):
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


class MemoryExtractor(dspy.Module):
    """
    ChainOfThought memory extractor — reasons about what makes a memory salient.
    """

    def __init__(self) -> None:
        super().__init__()
        self.extract = dspy.Predict(MemoryExtractionSignature)

    def forward(
        self,
        narrative_text: str,
        resolution: str,
        actor_name: str,
        role: Optional[ModelRole] = None,
    ) -> List[Dict[str, Any]]:
        with dspy_context_for("memory_extraction", role or ModelRole.STANDARD):
            prediction = self.extract(
                narrative_text=narrative_text,
                resolution=resolution,
                actor_name=actor_name,
            )

            # Safely parse the output into a list of dicts
            raw_memories = prediction.memories
            try:
                # Try to find JSON block if the LLM added prose
                if "```json" in raw_memories:
                    raw_memories = raw_memories.split("```json")[1].split("```")[0].strip()
                elif "```" in raw_memories:
                    raw_memories = raw_memories.split("```")[1].split("```")[0].strip()

                memories = json.loads(raw_memories)
                if not isinstance(memories, list):
                    return []
                return memories
            except (json.JSONDecodeError, IndexError) as e:
                logger.warning("Failed to parse memories from LLM output: %s", e)
                # Fallback: if it's not JSON, maybe it's just a string we can treat as a single memory
                if raw_memories and len(raw_memories) > 10:
                    return [
                        {
                            "text": raw_memories[:500],
                            "importance": 5,
                            "emotional_valence": 0.0,
                        }
                    ]
                return []
