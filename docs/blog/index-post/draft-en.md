# Building MONITOR: The Architecture Behind an AI Game Master

I have been building something called **MONITOR** for a while now: a system capable of running a full tabletop RPG campaign with persistent memory, coherent narration, and rules that actually apply, without needing a human being on the other side of the table.

Anyone can open ChatGPT, say "You are a Dungeon Master," and play for a while. But if you have tried it, you know the illusion breaks fast. The model forgets NPCs, invents rules that don't exist, allows your character to do impossible things, and ends up leaking plot secrets because it doesn't understand the difference between what *is true* and what *you know*.

To solve that, I stopped treating LLMs as magic chatbots and started treating them as components in a deterministic software architecture.

MONITOR is not a giant *prompt*. It is an engine powered by an ontological graph in Neo4j, databases in MongoDB, an agent system in LangGraph, and hard Python code that rolls actual dice.

This is the complete series where I document how I built the system, the architectural problems I encountered, and why I decided to build it from scratch.

---

## Part I: The Foundations
How we moved from hallucinating chats to structured databases.

1. **[From tabletop gaming to Ontological Graphs: how I started building an AI Game Master](./post-01)**
   The structural memory problem in LLMs and why a narrative "world" is best modeled as a Directed Acyclic Graph (DAG).
2. **[The ontological model and the agent system: how MONITOR grew](./post-02)**
   From a paper model to Neo4j. The creation of the `CanonKeeper` as a barrier against hallucinations and the vital distinction between Archetypes and Instances.
3. **[The Three-Layer Architecture: Why separate agents from data](./post-03)**
   Why frameworks like AutoGen or CrewAI fail in RPGs. The need for a strict state machine using LangGraph.

## Part II: Technical Deep Dives
Specific engineering problems and how we solved them by isolating LLM stochastics from code determinism.

4. **[The Split Brain of a Game Master: Why an LLM can't roll dice and tell stories at the same time](./post-04-split-brain)**
   The separation between the `GMAgent` (Narrator) and the `Resolver` (Referee). Why forcing a model to calculate math destroys its prose.
5. **[How do you unit test a Game Master? E2E Testing with LLM vs LLM](./post-05-testing)**
   Building a deterministic cage and using a chaotic LLM to try to break the bars. How we prove the Neo4j state doesn't corrupt.
6. **[How to teach an AI to read a rulebook (and why traditional RAG doesn't work)](./post-06-ingestion)**
   Why "naive chunking" creates useless text soup, and how we built a multimodal pipeline to extract hard rules to JSON.
7. **[The Ontology of Truth: How to stop an AI from leaking plot secrets](./post-07-ontology-of-truth)**
   Handling lies in a vector space. The use of canon levels (`canon`, `derived`, `rumor`) and belief graphs to protect the plot.
8. **[Stop Writing Prompts, Start Writing Types: Using DSPy](./post-08-dspy)**
   How we abandoned fragile prompt engineering and adopted strict Python typing to force the LLM to return valid data structures using DSPy.

## Part III: Closing

9. **[The CLI, the Tests, and Current State: What works and what is missing](./post-09-current-state)**
   A look at the interface, the inference latency problem, and the future roadmap for Co-Pilot mode.

---
*If you are interested in following the development or seeing how it is built under the hood, the complete repository is public: [github.com/spuentesp/monitor_dm_system](https://github.com/spuentesp/monitor_dm_system)*
