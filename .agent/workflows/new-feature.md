---
description: Create a new feature branch with proper naming
---

# New Feature Workflow

Guides you through starting work on a new feature with proper branch naming and use case identification.

## Steps

### 1. Identify the Use Case ID

Determine which use case your feature implements:

- **Data Layer**: `DL-1` to `DL-14` (canonical data access, MCP interfaces)
- **Play**: `P-1` to `P-12` (core gameplay loop)
- **Manage**: `M-1` to `M-30` (world administration)
- **Query**: `Q-1` to `Q-9` (canon exploration)
- **Ingest**: `I-1` to `I-6` (knowledge import)
- **System**: `SYS-1` to `SYS-10` (app lifecycle)
- **Co-Pilot**: `CF-1` to `CF-5` (GM assistant)
- **Story**: `ST-1` to `ST-5` (planning, meta-narrative)
- **Rules**: `RS-1` to `RS-4` (game system definition)
- **Docs**: `DOC-1` (documentation publishing)

**Reference**: See `docs/USE_CASES.md` for complete list.

### 2. Create Feature Branch

Branch naming format: `feature/<USE-CASE-ID>-short-description`

Examples:
- `feature/P-6-answer-question`
- `feature/DL-3-query-entities`
- `feature/M-15-create-faction`

```bash
git checkout main
git pull origin main
git checkout -b feature/<USE-CASE-ID>-<description>
```

### 3. Determine Affected Layers

Identify which layer(s) this feature touches:

**Layer 1 (data-layer)**: Database clients, MCP tools, schemas
- Required if: Adding new database operations, new MCP tools
- Location: `packages/data-layer/`

**Layer 2 (agents)**: AI agents, loops, prompts
- Required if: Adding agent logic, LLM interactions, game loops
- Location: `packages/agents/`

**Layer 3 (cli)**: User commands, REPL, UI
- Required if: Adding CLI commands, user-facing features
- Location: `packages/cli/`

**Most features touch multiple layers!** Implement from bottom to top: data-layer → agents → cli

### 4. Read Relevant Documentation

Based on affected layers, read:

**For data-layer work**:
- `docs/architecture/DATA_LAYER_API.md`
- `docs/architecture/VALIDATION_SCHEMAS.md`
- `packages/data-layer/README.md`

**For agent work**:
- `docs/architecture/AGENT_ORCHESTRATION.md`
- `docs/architecture/CONVERSATIONAL_LOOPS.md`
- `packages/agents/README.md`

**For CLI work**:
- `docs/USE_CASES.md` (your specific category)
- `packages/cli/README.md`

**For all work**:
- `.agent/rules.md` (MANDATORY!)
- `ARCHITECTURE.md`
- `CLAUDE.md`

### 5. Choose Implementation Workflow

Based on your starting layer, use the appropriate workflow:

- `/implement-data-layer` - Start with data access layer
- `/implement-agent` - Start with agent logic
- `/implement-cli` - Start with user interface

**Tip**: Most features start with data-layer, then agents, then CLI.

### 6. Commit Message Format

Include use case ID in commit messages:

```bash
git commit -m "[P-6] Add question answering functionality"
git commit -m "[DL-3] Implement entity query with filters"
```

## Branch Naming Examples

✅ **Good**:
- `feature/P-6-answer-question`
- `feature/DL-3-entity-query-filters`
- `feature/M-15-faction-creation`
- `bugfix/P-2-fix-scene-loop`

❌ **Bad**:
- `fix-bug` (no use case ID)
- `new-feature` (no use case ID)
- `feature/add-entities` (no use case ID)

## Next Steps

1. Implement feature using layer-specific workflows
2. Write tests for all changes
3. Run `/pre-commit-checks` before pushing
4. Create PR using `.github/pull_request_template.md`
5. Reference use case ID in PR description
