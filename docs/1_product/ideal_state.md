---
description: "Examples of how the three main modes should ideally operate."
tags: [product, ideal-state, use-cases]
layer: 0
---

# Ideal State & Target Use Cases

This outlines what the system must do across its primary modes.

## Mode 1: World Architect
**Goal:** Build and maintain fictional worlds from structured and unstructured sources.
- **Document Ingestion (`I-1` to `I-13`)**: Upload PDFs, chunk text, generate embeddings, extract entities, facts, and relationships.
- **Knowledge Pack Curation (`I-12`)**: Review and refine extracted data into reusable knowledge packs.
- **Knowledge Pack Application (`MP-5` to `MP-9`)**: Apply packs to a world, resolve conflicts, commit to canon.
- **World State Persistence**: Facts persist and remain consistent across sessions.

## Mode 2: Autonomous GM (Solo Roleplay)
**Goal:** Run a complete RPG session without a human GM.
- **Turn Loop (`P-3`)**: The core interaction. Parses action intent (dialogue, question, action, command) and delegates.
- **Resolve Action (`P-4`)**: Computes DCs, rolls dice, evaluates success margins, and creates `ProposedChanges`.
- **AutoGM Oracle (`P-18`)**: Answers questions about unknown environmental states using tension-based probability.
- **Forced Narrative Pushback (`P-20`)**: Prevents players from declaring high-stakes results without rolling.

## Mode 3: Game Master Assistant (Co-Pilot)
**Goal:** Augment a human DM by capturing sessions and suggesting hooks.
- **Record Session (`CF-1`)**: Parses GM notes/transcripts to draft scenes and propose facts.
- **Generate Recap (`CF-2`)**: Summarizes scenes, decisions, and threads.
- **Detect Unresolved Threads (`CF-3`)**: Finds open questions or dangling hooks.
- **Suggest Plot Hooks (`CF-4`)**: Generates contextual hooks based on unresolved threads and recent events.
- **Detect Contradictions (`CF-5`)**: Identifies conflicting facts and suggests resolutions.

## See Also
- [Vision & Modes](./vision_and_modes.md)
