"""
Ingest jobs CLI for MONITOR.

LAYER: 3 (cli)
IMPORTS FROM: monitor_agents (Layer 2), rich, typer, stdlib.

Commands:
    $ monitor ingest list [--status ...] [--stale] [--json]
    $ monitor ingest show <job_id>
    $ monitor ingest cancel <job_id>

These surface the same information the /api/jobs/health endpoint
returns, so operators don't have to spin up the UI to see what
ingestion jobs are doing.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(help="Inspect and manage in-flight ingestion jobs")
console = Console()


def _stale_threshold_seconds() -> float:
    return float(os.environ.get("MONITOR_INGEST_STALE_AFTER_SECONDS", str(45 * 60)))


def _stale_cutoff() -> datetime:
    return datetime.now(UTC) - timedelta(seconds=_stale_threshold_seconds())


def _is_stale(doc: dict[str, Any], cutoff: datetime) -> bool:
    """A running job is stale if its last progress timestamp is
    older than the cutoff. Falls back to started_at."""
    if doc.get("status") != "running":
        return False
    last = doc.get("stage_last_progress_at") or doc.get("started_at")
    if last is None:
        return False
    if last.tzinfo is None:
        last = last.replace(tzinfo=UTC)
    return bool(last < cutoff)


def _fetch_jobs(filter_status: str | None, only_stale: bool) -> list[dict[str, Any]]:
    """Read ingestion_jobs directly through the data-layer accessor.
    The CLI is allowed to read; cancellation flows through agents.
    """
    # Lazy imports so the CLI stays importable without env vars loaded.
    from monitor_data.db.mongodb import get_mongodb_client

    coll = get_mongodb_client().get_collection("ingestion_jobs")
    query: dict[str, Any] = {}
    if filter_status:
        query["status"] = filter_status
    cursor = coll.find(query).sort("started_at", -1).limit(200)
    cutoff = _stale_cutoff()
    docs = list(cursor)
    if only_stale:
        docs = [d for d in docs if _is_stale(d, cutoff)]
    return docs


def _format_age(ts: datetime | None, ref: datetime | None = None) -> str:
    if ts is None:
        return "—"
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    if ref is None:
        ref = datetime.now(UTC)
    delta = ref - ts
    minutes = delta.total_seconds() / 60
    if minutes < 1:
        return f"{int(delta.total_seconds())}s"
    if minutes < 60:
        return f"{minutes:.0f}m"
    return f"{minutes / 60:.1f}h"


@app.command("list")
def list_jobs(
    status_filter: str | None = typer.Option(
        None,
        "--status",
        help="Filter by status (pending|running|failed|completed|partial)",
    ),
    stale: bool = typer.Option(False, "--stale", help="Show only stale running jobs (no progress > threshold)"),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON instead of a table"),
    limit: int = typer.Option(50, "--limit", "-n", help="Max rows to show"),
) -> None:
    """List recent ingestion jobs."""
    docs = _fetch_jobs(status_filter, only_stale=stale)
    docs = docs[:limit]
    if json_output:
        out = []
        cutoff = _stale_cutoff()
        for d in docs:
            out.append(
                {
                    "job_id": str(d.get("job_id") or d.get("_id")),
                    "status": d.get("status"),
                    "source_title": d.get("source_title", ""),
                    "started_at": (d["started_at"].isoformat() if d.get("started_at") is not None else None),
                    "stage_last_progress_at": (
                        d["stage_last_progress_at"].isoformat() if d.get("stage_last_progress_at") is not None else None
                    ),
                    "stale": _is_stale(d, cutoff),
                    "kill_reason": d.get("kill_reason"),
                    "last_error": d.get("last_error"),
                }
            )
        console.print_json(json.dumps(out, indent=2, default=str))
        return

    if not docs:
        console.print("[yellow]No jobs match.[/yellow]")
        return

    cutoff = _stale_cutoff()
    table = Table(title="Ingestion Jobs", show_lines=False)
    table.add_column("Job ID", style="cyan", no_wrap=True)
    table.add_column("Status")
    table.add_column("Source", overflow="ellipsis")
    table.add_column("Stage", overflow="ellipsis")
    table.add_column("Last progress")
    table.add_column("Stale")
    table.add_column("Kill reason")

    for d in docs:
        status = d.get("status", "?")
        if status == "running":
            status_rendered = f"[yellow]{status}[/yellow]"
        elif status == "failed":
            status_rendered = f"[red]{status}[/red]"
        elif status == "completed":
            status_rendered = f"[green]{status}[/green]"
        else:
            status_rendered = status

        job_id = str(d.get("job_id") or d.get("_id"))[:8]
        last_progress = d.get("stage_last_progress_at") or d.get("started_at")
        stale_rendered = (
            "[red]stale[/red]" if _is_stale(d, cutoff) else ("—" if status != "running" else "[green]fresh[/green]")
        )

        table.add_row(
            job_id,
            status_rendered,
            (d.get("source_title") or "")[:40],
            (d.get("current_stage") or "—")[:24],
            _format_age(last_progress),
            stale_rendered,
            d.get("kill_reason") or "",
        )
    console.print(table)


@app.command("show")
def show_job(
    job_id: str = typer.Argument(..., help="Ingestion job UUID"),
) -> None:
    """Show full details of a single ingestion job."""
    from monitor_data.db.mongodb import get_mongodb_client

    coll = get_mongodb_client().get_collection("ingestion_jobs")
    try:
        uuid_obj = UUID(job_id)
    except ValueError:
        console.print(f"[red]Invalid job UUID:[/red] {job_id}")
        raise typer.Exit(1)

    doc = coll.find_one({"job_id": uuid_obj})
    if not doc:
        # Fallback: search by _id
        try:
            doc = coll.find_one({"_id": uuid_obj})
        except Exception:
            doc = None
    if not doc:
        console.print(f"[red]Job {job_id} not found.[/red]")
        raise typer.Exit(1)

    console.print_json(json.dumps(doc, indent=2, default=str))


@app.command("cancel")
def cancel_job(
    job_id: str = typer.Argument(..., help="Ingestion job UUID to cancel"),
) -> None:
    """Cancel a running ingestion job (delegates to the API endpoint)."""
    try:
        UUID(job_id)
    except ValueError:
        console.print(f"[red]Invalid job UUID:[/red] {job_id}")
        raise typer.Exit(1)

    import httpx

    base = os.environ.get("MONITOR_API_BASE", "http://localhost:8000")
    url = f"{base}/api/ingest/jobs/{job_id}/cancel"
    try:
        resp = httpx.post(url, timeout=30)
    except httpx.HTTPError as exc:
        console.print(f"[red]Cannot reach API at {base}:[/red] {exc}")
        raise typer.Exit(1)
    if resp.status_code >= 400:
        console.print(f"[red]API error {resp.status_code}:[/red] {resp.text[:200]}")
        raise typer.Exit(1)
    console.print(f"[green]Cancelled job {job_id}.[/green]")


__all__ = ["app"]
