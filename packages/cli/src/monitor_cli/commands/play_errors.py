"""
Roleplay error CLI for MONITOR.

LAYER: 3 (cli)
IMPORTS FROM: monitor_data (Layer 1, read-only — same accepted exception as
    ingest_jobs.py: "the CLI is allowed to read, writes flow through agents"),
    rich, typer, stdlib.

Commands:
    $ monitor play errors [--source ...] [--category ...] [--story-id ...]
        [--scene-id ...] [--fatal] [--json] [--limit N]

Registers onto the same Typer app as commands/play.py (imported by
main.py so this module's decorator runs) — `monitor play errors` sits
next to `monitor play start`.

Surfaces the roleplay_errors collection: structured failure records
persisted by RoleplayErrorRecorder from the live play loop (scene_loop,
gm_agent, resolver, narrator, canonkeeper) and light-RP character
conversations. See monitor_data.schemas.roleplay_errors for the record
shape and why a dedicated collection was chosen.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import typer
from monitor_cli.commands.play import app
from rich.console import Console
from rich.table import Table

console = Console()


def _fetch_roleplay_errors(
    source: str | None,
    category: str | None,
    story_id: str | None,
    scene_id: str | None,
    conversation_id: str | None,
    fatal_only: bool,
    limit: int,
) -> list[dict[str, Any]]:
    """Read roleplay_errors directly through the data-layer accessor.
    The CLI is allowed to read; recording flows through RoleplayErrorRecorder.
    """
    # Lazy import so the CLI stays importable without env vars loaded.
    from monitor_data.db.mongodb import get_mongodb_client

    coll = get_mongodb_client().get_collection("roleplay_errors")
    query: dict[str, Any] = {}
    if source:
        query["source"] = source
    if category:
        query["category"] = category
    if story_id:
        query["story_id"] = story_id
    if scene_id:
        query["scene_id"] = scene_id
    if conversation_id:
        query["conversation_id"] = conversation_id
    if fatal_only:
        query["fatal"] = True

    cursor = coll.find(query).sort("occurred_at", -1).limit(limit)
    return list(cursor)


def _format_age(ts: datetime | None) -> str:
    if ts is None:
        return "—"
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    delta = datetime.now(UTC) - ts
    minutes = delta.total_seconds() / 60
    if minutes < 1:
        return f"{int(delta.total_seconds())}s"
    if minutes < 60:
        return f"{minutes:.0f}m"
    if minutes < 1440:
        return f"{minutes / 60:.1f}h"
    return f"{minutes / 1440:.1f}d"


@app.command("errors")
def list_roleplay_errors(
    source: str | None = typer.Option(
        None,
        "--source",
        help="Filter by source (scene_loop|gm_agent|resolver|narrator|canonkeeper|preplay_support|character_conversation)",
    ),
    category: str | None = typer.Option(None, "--category", help="Filter by RoleplayErrorCategory value"),
    story_id: str | None = typer.Option(None, "--story-id", help="Filter by story UUID"),
    scene_id: str | None = typer.Option(None, "--scene-id", help="Filter by scene UUID"),
    conversation_id: str | None = typer.Option(None, "--conversation-id", help="Filter by light-RP conversation id"),
    fatal: bool = typer.Option(False, "--fatal", help="Show only fatal errors"),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON instead of a table"),
    limit: int = typer.Option(50, "--limit", "-n", help="Max rows to show", min=1, max=200),
) -> None:
    """List recent structured roleplay errors (Play + light-RP)."""
    if story_id:
        try:
            UUID(story_id)
        except ValueError:
            console.print(f"[red]Invalid story UUID:[/red] {story_id}")
            raise typer.Exit(1)
    if scene_id:
        try:
            UUID(scene_id)
        except ValueError:
            console.print(f"[red]Invalid scene UUID:[/red] {scene_id}")
            raise typer.Exit(1)

    docs = _fetch_roleplay_errors(source, category, story_id, scene_id, conversation_id, fatal, limit)

    if json_output:
        out = [
            {
                "error_id": d.get("error_id"),
                "occurred_at": (d["occurred_at"].isoformat() if d.get("occurred_at") is not None else None),
                "source": d.get("source"),
                "category": d.get("category"),
                "llm_error_class": d.get("llm_error_class"),
                "message": d.get("message"),
                "fatal": d.get("fatal", False),
                "story_id": d.get("story_id"),
                "scene_id": d.get("scene_id"),
                "conversation_id": d.get("conversation_id"),
            }
            for d in docs
        ]
        console.print_json(json.dumps(out, indent=2, default=str))
        return

    if not docs:
        console.print("[yellow]No roleplay errors match.[/yellow]")
        return

    table = Table(title="Roleplay Errors", show_lines=False)
    table.add_column("Age")
    table.add_column("Source")
    table.add_column("Category")
    table.add_column("Fatal")
    table.add_column("Message", overflow="ellipsis")
    table.add_column("Story/Scene", overflow="ellipsis")

    for d in docs:
        fatal_rendered = "[red]yes[/red]" if d.get("fatal") else "no"
        correlation = d.get("story_id") or d.get("conversation_id") or ""
        if d.get("scene_id"):
            correlation = f"{correlation}/{d['scene_id']}" if correlation else d["scene_id"]
        table.add_row(
            _format_age(d.get("occurred_at")),
            d.get("source", "?"),
            d.get("category", "?"),
            fatal_rendered,
            (d.get("message") or "")[:80],
            (correlation or "")[:20],
        )
    console.print(table)


__all__ = ["app"]
