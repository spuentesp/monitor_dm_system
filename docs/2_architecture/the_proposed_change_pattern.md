---
description: "The core design pattern for safely mutating the canonical graph."
tags: [architecture, data-flow, pattern, canonkeeper]
layer: 1
---

# The Proposed Change Pattern

To ensure the Neo4j Knowledge Graph remains clean, consistent, and strictly canonical, MONITOR employs the **Proposed Change Pattern**.

## The Core Rule
**No agent (except the CanonKeeper) can write directly to Neo4j.**

## How It Works
1. **Agents Propose**: Agents (like the Narrator, Resolver, or Analyzer) generate structural mutations but write them to MongoDB as `ProposedChange` documents.
2. **Review**: The CanonKeeper agent evaluates these proposals against established policies (e.g., checking for contradictions, enforcing constraints).
3. **Commit**: The CanonKeeper commits accepted proposals to Neo4j and marks them `accepted` in MongoDB.

## Why This Matters
- Prevents rogue agents or hallucinating LLMs from corrupting the core graph.
- Allows for Human-in-the-Loop review (in Co-Pilot mode, the GM can review `ProposedChange` documents before they are canonized).

## See Also
- [Layer 1: Data](./layer1_data.md)
