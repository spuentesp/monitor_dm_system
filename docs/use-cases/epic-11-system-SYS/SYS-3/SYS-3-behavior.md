# SYS-3: Exit Application — Behavior Specification

> Verifies that actual implementation matches the behavior defined in SYS-3-specification.md

## Scenario 1: Application Exit

**Given** the user is in the application
**When** the user selects exit or presses Ctrl+C
**Then** progress is saved and connections are closed cleanly

### AC-1: Exit Prompt
- [x] User is prompted to save progress if in active scene
- [x] Auto-save occurs if configured
- [x] User can cancel exit

### AC-2: Connection Cleanup
- [x] Neo4j connection is closed
- [x] MongoDB connection is closed
- [x] Qdrant connection is closed (if used)

### AC-3: Clean Exit
- [x] Application exits with code 0
- [x] No dangling processes
- [x] Logged exit event