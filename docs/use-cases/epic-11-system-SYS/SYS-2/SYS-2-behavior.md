# SYS-2: Main Menu — Behavior Specification

> Verifies that actual implementation matches the behavior defined in SYS-2-specification.md

## Scenario 1: Main Menu Display

**Given** the application has started
**When** the user is at the main menu
**Then** all menu options are displayed and accessible

### AC-1: Menu Options
- [x] [P] Play - Start or continue story
- [x] [M] Manage - Universes, stories, entities
- [x] [Q] Query - Search and explore canon
- [x] [I] Ingest - Upload documents
- [x] [S] Settings - Configuration
- [x] [X] Exit - Exit application

### AC-2: Menu Navigation
- [x] User can select options by letter
- [x] Invalid input is handled gracefully
- [x] Menu redraws after submenu returns

### AC-3: Option Routing
- [x] P routes to play menu/flow
- [x] M routes to manage menu
- [x] Q routes to query interface
- [x] I routes to ingest interface
- [x] S routes to settings
- [x] X exits the application