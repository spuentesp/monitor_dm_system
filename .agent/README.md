# MONITOR Agent Infrastructure

This directory contains workflows and rules specifically designed for AI agents working on the MONITOR project.

## Purpose

The `.agent` directory provides:
- **Workflows**: Standardized procedures for common development tasks
- **Rules**: MONITOR-specific constraints and patterns AI agents must follow

## Using Workflows

Workflows are markdown files with YAML frontmatter that define step-by-step procedures. You can trigger them using slash commands:

```bash
# Example: Start infrastructure
/start-infra

# Example: Run tests
/run-tests
```

AI agents can execute these workflows automatically or guide you through them interactively.

## Available Workflows

| Workflow | Slash Command | Description |
|----------|---------------|-------------|
| **start-infra** | `/start-infra` | Start all Docker database services |
| **run-tests** | `/run-tests` | Run complete test suite for all layers |
| **check-dependencies** | `/check-dependencies` | Validate layer boundary compliance |
| **new-feature** | `/new-feature` | Create a new feature branch with proper naming |
| **implement-data-layer** | `/implement-data-layer` | Implement a data-layer feature |
| **implement-agent** | `/implement-agent` | Implement agent functionality |
| **implement-cli** | `/implement-cli` | Implement a CLI command |
| **pre-commit-checks** | `/pre-commit-checks` | Run all validation checks |
| **sync-docs** | `/sync-docs` | Sync documentation to GitHub wiki |

## Rules

The `rules.md` file contains MONITOR-specific rules that AI agents must follow:

- **Layer Boundaries**: Strict 3-layer architecture enforcement
- **CanonKeeper Authority**: Only CanonKeeper writes to Neo4j
- **Use Case References**: All work must reference a use case ID
- **Testing Requirements**: Every code change needs tests
- **Evidence-Based Canonization**: All canonical facts need provenance

## For AI Agents

Before starting work on MONITOR:

1. **Read** `.agent/rules.md` - Critical project-specific constraints
2. **Read** project root `ARCHITECTURE.md` - Layer architecture
3. **Read** project root `CLAUDE.md` - Detailed AI agent instructions
4. **Identify** which layer your changes belong to
5. **Use** workflows to ensure consistent development practices

## For Humans

You can use workflows to:
- Standardize onboarding for new developers
- Ensure consistent CI/CD practices
- Guide AI agents through complex procedures
- Document common development patterns

## Directory Structure

```
.agent/
├── README.md           # This file
├── rules.md            # MONITOR-specific rules for AI agents
└── workflows/          # Development workflow definitions
    ├── start-infra.md
    ├── run-tests.md
    ├── check-dependencies.md
    ├── new-feature.md
    ├── implement-data-layer.md
    ├── implement-agent.md
    ├── implement-cli.md
    ├── pre-commit-checks.md
    └── sync-docs.md
```

## Workflow Format

Each workflow follows this format:

```markdown
---
description: [short title describing the workflow]
---

# Workflow Name

[Detailed instructions with numbered steps]

1. First step
2. Second step
   - Sub-step if needed
3. Third step

// turbo       ← Optional: auto-run the next step if it's safe
4. Safe automated step
```

The `// turbo` annotation tells AI agents that a command is safe to run automatically without user approval.

## Contributing

When adding new workflows:
1. Follow the YAML frontmatter + markdown format
2. Use clear, numbered steps
3. Include expected outcomes
4. Add `// turbo` annotations for safe commands
5. Update this README with the new workflow

---

**Note**: This directory is designed to work with AI coding agents like Claude, ChatGPT, Copilot, etc. The workflows help ensure consistency and adherence to MONITOR's strict architectural requirements.
