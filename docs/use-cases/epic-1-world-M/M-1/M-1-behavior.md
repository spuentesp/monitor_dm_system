# M-1: Create Multiverse — Behavior Specification

> Verifies that actual implementation matches the behavior defined in M-1-specification.md

## Scenario 1: Multiverse Creation

**Given** a user wants to create a new multiverse/setting
**When** they go through the multiverse creation flow
**Then** a multiverse node is created in Neo4j linked to the Omniverse

### AC-1: Omniverse Retrieval
- [x] Omniverse is retrieved (or created if none exists)
- [x] Singleton pattern is enforced
- [x] Default name is "Omniverse"

### AC-2: Multiverse Creation
- [x] Multiverse name is validated (1-200 chars)
- [x] System/genre is recorded
- [x] Description is stored (optional)
- [x] Created timestamp is set

### AC-3: Link to Omniverse
- [x] Multiverse is linked to Omniverse with CONTAINS relationship

### AC-4: Return Value
- [x] Created multiverse ID is returned
- [x] Multiverse details are available for confirmation