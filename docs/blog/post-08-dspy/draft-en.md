# Stop Writing Prompts, Start Writing Types: Using DSPy

If you have spent more than an hour building applications with language models, you know the pain of *prompt engineering*.

You start with a simple instruction: *"You are a Game Master. Describe what happens."*
Then you realize the model talks too much, so you add: *"Keep your answer under 3 paragraphs."*
Then you need to integrate it with your Python code, so you beg: *"Please reply ONLY in JSON format. Do not use markdown blocks. Make sure to include the 'intent' key."*

Eventually, your *system prompt* is a fragile 2,000-token monolith of stochastic pleading. And when you switch models (say, from GPT-4 to Claude), everything breaks, because every model reacts differently to your begging.

To build MONITOR, where dozens of agents have to pass structured data to each other flawlessly so the game doesn't collapse, begging the model was not an option. I needed the LLMs to behave like strictly typed Python functions.

The solution was **DSPy**.

## What is DSPy?

[DSPy](https://github.com/stanfordnlp/dspy) is a framework developed by Stanford that fundamentally changes how you interact with LLMs. Instead of hand-crafting prompts, you define **Signatures**.

A signature is simply a declaration of what variables go in (Inputs) and what variables must come out (Outputs). DSPy takes care of compiling the optimal prompt under the hood.

## Strict Typing in MONITOR

If you look at the agent directories in the MONITOR codebase (e.g., `packages/agents/src/monitor_agents/analyzer/`), you'll notice something strange: there are almost no traditional "prompts." Instead, there are strongly typed Python classes co-located with their agents.

Look at how the `Analyzer` agent (in charge of deciding if the player did something that requires a dice roll) is defined:

```python
import dspy

class ActionAnalyzer(dspy.Signature):
    """Analyzes player action and determines if it requires mechanical resolution based on the rules."""
    
    context = dspy.InputField(desc="Relevant facts, entities, and scene state")
    rules = dspy.InputField(desc="Relevant game mechanics extracted from Qdrant")
    player_action = dspy.InputField(desc="The raw declaration from the player")
    
    requires_roll = dspy.OutputField(desc="Boolean, true if the action has a chance of failure and requires dice")
    selected_mechanic = dspy.OutputField(desc="The mechanic_id to execute, if applicable")
    rationale = dspy.OutputField(desc="Why this decision was made")
```

I am not telling the LLM "think step by step and give me a JSON back". I just define the `InputField` and `OutputField`.

When I call this agent using our internal `dspy_runtime` engine, DSPy dynamically generates a structured prompt, forces the model to adhere to the structure, and if the model hallucinates and returns text instead of a boolean in `requires_roll`, the framework can self-correct and ask it to fix the type error.

## The End of Prompt Engineering

The biggest advantage of this architecture is model agnosticism. When I built the `CanonKeeper`, I used GPT-4. Later, I wanted to see if Claude 3.5 Sonnet was faster. If I had used manual prompts, I would have had to rewrite them all to fit Claude's "personality."

With DSPy, I only changed the engine in `dspy_context_for`. The Signatures remained exactly the same. The framework handled the adaptation.

When you isolate natural language from strict typing, LLMs stop being unpredictable "magic chatbots" and become predictable, compilable modules of your software architecture. Stop writing prompts. Start writing types.

---

### References and Code Links
- **[analyzer.py](https://github.com/spuentesp/monitor_dm_system/blob/main/packages/agents/src/monitor_agents/analyzer/analyzer.py)**: The module where we implement DSPy signatures for strict intent analysis.
- **[dspy_runtime.py](https://github.com/spuentesp/monitor_dm_system/blob/main/packages/agents/src/monitor_agents/dspy_runtime.py)**: The base runtime environment that initializes the underlying model.
- [Khattab et al. (Stanford NLP)](https://arxiv.org/abs/2310.03714): *DSPy: Compiling Declarative Language Model Calls into State-of-the-Art Pipelines*.
