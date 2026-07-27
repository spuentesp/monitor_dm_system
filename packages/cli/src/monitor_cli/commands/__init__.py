"""
CLI Commands for MONITOR.

Each command module provides a Typer sub-application:
- play:   Interactive story sessions (REPL)
- ingest: Document upload and processing
- query:  Canon querying and exploration
- manage: Entity and universe management

All commands interact with agents, never directly with databases.
"""
