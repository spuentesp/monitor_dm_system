# The Reasoning Brain: Prompt Engineering

This document explains how MONITOR utilizes advanced prompt engineering frameworks to achieve consistent reasoning and structured data output across multiple LLM providers.

---

## 1. The Core Stack

We use a three-tier stack for all AI interactions:

1. **Reasoning Layer (DSPy):** Handles the "thought process."
2. **Structure Layer (instructor):** Handles the "output format."
3. **Transport Layer (LiteLLM):** Handles the "API connection."

---

## 2. DSPy: Declarative Reasoning

Instead of traditional string-based prompting, MONITOR uses **DSPy Signatures and Modules**. 

- **Signatures:** Define the *input* and *output* variables (e.g., `Context` + `Action` → `Prose`).
- **Modules:** Define the *reasoning pattern* (e.g., `ChainOfThought`, `ProgramOfThought`).
- **Optimization:** Using DSPy allows us to "compile" prompts, meaning we can optimize them for specific models (like GPT-4o vs Claude 3.5 Sonnet) automatically using metrics.

---

## 3. instructor: Strict Schema Enforcement

While DSPy generates the creative reasoning, we use the **instructor** library to ensure the LLM returns valid Pydantic models.

### Example Interaction Pattern
1. **Narrator** thinks through the turn (DSPy ChainOfThought).
2. **Narrator** generates the prose.
3. **Narrator** uses `instructor` to extract structured `ProposedChange` objects (Facts, Entities) from that prose.

This separation ensures that creative writing doesn't break the structural data integrity of the Knowledge Graph.

---

## 4. Provider-Agnostic Routing (LLM Registry)

The `LLMRegistry` (`packages/agents/src/monitor_agents/llm_registry.py`) decouples agents from specific AI vendors.

### Task-Complexity Tiers (Model Roles)
We route tasks based on complexity to optimize for speed and cost:

- **ModelRole.LIGHT (Haiku/Flash):** Used for simple NPC dialogue and intent parsing.
- **ModelRole.STANDARD (Sonnet/GPT-4o):** Used for narration and general reasoning.
- **ModelRole.HEAVY (Opus/Ultra):** Reserved for complex world-building and knowledge extraction.

### Dynamic Re-routing
If a provider is down, the registry can automatically fall back to an equivalent model from another vendor without changing the agent's code.

---

## 5. DSPy Runtime Context

We use a custom `dspy_context_for` helper (`packages/agents/src/monitor_agents/dspy_runtime.py`) to manage global DSPy state safely within an asynchronous multi-agent environment. This ensures that:
- Each agent call uses the correct model.
- Traceability (Logfire) is maintained across the call stack.
- Retries and rate-limiting are handled uniformly.

---

## 6. Prompt Versioning & Governance

- **Location:** All DSPy modules live in `packages/agents/src/monitor_agents/prompts/`.
- **Testing:** We use `monitor playtest` to benchmark prompt changes against gold-standard narrative examples.
- **Deployment:** Prompt "compilation" results can be saved as JSON configurations, allowing us to update AI behavior without redeploying code.
