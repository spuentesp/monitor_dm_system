# M-2: Create Universe — Behavior Specification

> Verifies that actual implementation matches the behavior defined in M-2-specification.md

## Scenario 1: Universe Creation

**Given** a user wants to create a new universe within a multiverse
**When** they go through the universe creation flow
**Then** a universe node is created in Neo4j linked to the Multiverse

### AC-1: Multiverse Selection
- [x] User can list multiverses
- [x] User can select a multiverse
- [x] Invalid multiverse ID is rejected

### AC-2: Universe Parameters
- [x] Universe name is validated
- [x] Genre is recorded (Fantasy, Sci-Fi, etc.)
- [x] Tone is recorded (Dark, Heroic, etc.)
- [x] Tech level is recorded

### AC-3: Fresh Start vs Branching
- [x] Fresh start creates clean universe
- [x] Branching links to source universe with BRANCH_OF relationship

### AC-4: Universe Creation
- [x] Universe node is created in Neo4j
- [x] Universe is linked to Multiverse
- [x] Created timestamp is set

### AC-5: Return Value
- [x] Created universe ID is returned