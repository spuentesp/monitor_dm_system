import json
import logging
import uuid
from typing import Any

import dspy

logger = logging.getLogger(__name__)


class ExtractMechanics(dspy.Signature):
    """Extract mechanical TTRPG rules from text into structured JSON."""
    
    text: str = dspy.InputField(desc="A chunk of text from a TTRPG rulebook containing mechanics or hybrid rules.")
    
    json_output: str = dspy.OutputField(
        desc="A JSON block matching the GameSystemCreate schema for the extracted mechanics. Only return valid JSON without markdown wrapping."
    )


class MechanicsArchitect:
    """Agent that builds Game System schema objects from mechanical text."""
    
    def __init__(self) -> None:
        pass
        
    def extract(self, text: str) -> dict[str, Any]:
        """Extract mechanics from text and return a dictionary."""
        from monitor_agents.dspy_runtime import dspy_context_for
        
        with dspy_context_for("mechanics_architect"):
            predictor = dspy.Predict(ExtractMechanics)
            result = predictor(text=text)
            
            raw = result.json_output.strip()
            if raw.startswith("```json"):
                raw = raw[7:-3]
            elif raw.startswith("```"):
                raw = raw[3:-3]
                
            try:
                data = json.loads(raw)
                
                # If it's a hybrid power/discipline, ensure it has a deterministic ID
                if "name" in data and "id" not in data:
                    safe_name = data["name"].lower().replace(" ", "_")
                    data["id"] = f"power_{safe_name}_{uuid.uuid4().hex[:8]}"
                    
                return data  # type: ignore[no-any-return]
            except json.JSONDecodeError as exc:
                logger.warning(f"Mechanics extraction failed to decode JSON: {exc}")
                return {}
