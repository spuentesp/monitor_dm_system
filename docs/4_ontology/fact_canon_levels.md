---
description: "Explains how truth and certainty are graded in the system."
tags: [ontology, facts, canon]
layer: 1
---

# Fact Canon Levels

To allow the world to contain rumors, lies, and subjective character beliefs without corrupting objective reality, facts in MONITOR are assigned a `CanonLevel`.

## Levels of Canon
1. **Core / Axiom**: Unbreakable laws of the universe.
2. **Canon**: Verified, objective truth (established by the system or human GM).
3. **Derived**: Truth deduced by the system based on other facts.
4. **Rumor / Subjective**: What an entity *believes* to be true (may be false).
5. **Alternative / Proposed**: Used during what-if simulations or unreviewed `ProposedChange` drafts.

## Resolving Contradictions
When a higher-level canon fact contradicts a lower-level one, the higher level wins. `CanonKeeper` is responsible for evaluating these prior to Neo4j commits.

## See Also
- [Ontology Index](./_index.md)
