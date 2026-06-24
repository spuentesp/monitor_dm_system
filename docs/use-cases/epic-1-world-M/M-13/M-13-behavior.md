# M-13: Create Character — Behavior Specification

> Verifies that actual implementation matches the behavior defined in M-13-specification.md

## Scenario 1: Character Creation

**Given** a user wants to create a character in a universe
**When** they go through the character creation flow
**Then** a character entity is created with stats, resources, and optional archetype

### AC-1: Character Name and Role
- [x] Character name is validated (1-200 chars)
- [x] Role is set (PC, NPC, antagonist, ally)
- [x] Description is stored (optional)

### AC-2: Archetype Selection
- [x] Archetypes can be listed
- [x] Character can optionally link to archetype via DERIVES_FROM
- [x] Custom (non-archetype) characters are supported

### AC-3: Stats and Resources
- [x] Stats are recorded for PC/detailed NPC (STR, DEX, CON, INT, WIS, CHA)
- [x] Resources are calculated (HP, MP)
- [x] Stats validation ensures valid ranges

### AC-4: Entity Creation
- [x] EntityInstance is created in Neo4j with entity_type="character"
- [x] Character is linked to universe via HAS_ENTITY
- [x] Character sheet is created in MongoDB for PC/detailed NPC

### AC-5: Return Value
- [x] Created character ID is returned
- [x] Character details are available for confirmation