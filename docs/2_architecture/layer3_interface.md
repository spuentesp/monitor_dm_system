---
description: "Details Layer 3: Interface Layer."
tags: [architecture, interface, layer-3]
layer: 3
---

# Layer 3: Interface Layer

This layer acts as the user-facing surface for the entire MONITOR system.

## Components
- **monitor-cli**: A Typer-based CLI for running the system, entering REPLs, and executing specific offline commands.
- **monitor-ui-backend**: A FastAPI application that serves the frontend and handles WebSocket connections for live loops.
- **monitor-ui-frontend**: A Next.js web application for visual interaction, world building, and chat.

## Responsibilities
- Taking user input and passing it to the appropriate Layer 2 loops.
- Displaying streaming output from agents.
- Formatting structured data for human consumption.

## Strict Rules
- **Rule:** Imports from Layer 2.
- **Rule:** **Skip-Layer Protection:** Layer 3 must avoid importing directly from Layer 1. Operations requiring Layer 1 access must be routed through Layer 2 Agents or Loops.

## See Also
- [The Three Layers](./the_three_layers.md)
