# DOC-1: Agentic Documentation Organization

## Objective
Transform the project's documentation from large, monolithic, human-oriented files into small, highly-connected, agent-friendly files. This prevents LLMs from blowing through context windows when reading simple architectural context.

## Details
- All documentation is placed within the `docs/` folder, organized numerically (e.g. `1_product`, `2_architecture`).
- A central graph map is maintained at `docs/_index.md`.
- Stale audit files, old plans, and disconnected files are removed to prevent search dilution.
- Agents can navigate through simple markdown links `[link](file.md)`.
