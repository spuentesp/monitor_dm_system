---
description: "Details Layer 2: Agents, Loops, and Logic."
tags: [architecture, agents, layer-2, langgraph]
layer: 2
---

# Layer 2: Agent Layer (`monitor-agents`)

The "brain" of the system. It handles narrative intelligence, reasoning, and orchestration using stateless agents.

## Core Components
- **Agents**: Specialized, stateless workers (e.g., `ContextAssembly`, `Narrator`, `Resolver`, `CanonKeeper`).
- **Loops**: LangGraph StateGraph loops that manage control flow.
- **DSPy**: Used for creative reasoning chains (e.g., generating prose, extracting knowledge).
- **Instructor**: Enforces strict Pydantic output from LLMs for tool calls.
- **LiteLLM**: Provider-agnostic abstraction for LLM calls.

## Responsibilities
- **Orchestration**: Managing complex, multi-turn interactions.
- **Narrative Logic**: Applying rules, rolling dice, generating descriptions.
- **Knowledge Synthesis**: Assembling context from Layer 1 tools to feed to prompts.

## Strict Rules
- **Rule:** Imports from Layer 1.
- **Rule:** Never imports from Layer 3.
- **Rule:** Agents must be stateless. All persistence is handled via LangGraph Checkpointers (to MongoDB) or MCP tool calls.

## See Also
- [The Three Layers](./the_three_layers.md)
- [Loops & Systems Index](../3_loops_and_systems/_index.md)
