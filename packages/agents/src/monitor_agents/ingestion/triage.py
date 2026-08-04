import dspy

class TriageTag(dspy.Signature):
    """Classify a chunk of a TTRPG rulebook into one or more categories."""
    
    text: str = dspy.InputField(desc="A chunk of text from a TTRPG rulebook.")
    
    tags: str = dspy.OutputField(
        desc="A list of tags, choosing from: #lore, #mechanics, #hybrid, #example. Return as a comma-separated string."
    )

class TriageAgent:
    """Agent that triages raw document chunks into processing streams."""
    
    def __init__(self) -> None:
        pass
        
    def triage(self, text: str) -> list[str]:
        from monitor_agents.dspy_runtime import dspy_context_for
        
        with dspy_context_for("triage_agent"):
            predictor = dspy.Predict(TriageTag)
            result = predictor(text=text)
            
            raw_tags = result.tags.split(",")
            valid_tags = {"#lore", "#mechanics", "#hybrid", "#example"}
            
            tags = []
            for t in raw_tags:
                clean_t = t.strip().lower()
                if not clean_t.startswith("#"):
                    clean_t = f"#{clean_t}"
                if clean_t in valid_tags:
                    tags.append(clean_t)
                    
            if not tags:
                # Default to lore if unclear
                tags = ["#lore"]
                
            return tags
