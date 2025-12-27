"""
CLI Commands for MONITOR.

Each command module provides a Typer sub-application:
- play:   Interactive story sessions (REPL)
- ingest: Document upload and processing
- query:  Canon querying and exploration
- manage: Entity and universe management

All commands interact with agents, never directly with databases.
"""

# from monitor_cli.commands.play import app as play_app
# from monitor_cli.commands.ingest import app as ingest_app
# from monitor_cli.commands.query import app as query_app
# from monitor_cli.commands.manage import app as manage_app
