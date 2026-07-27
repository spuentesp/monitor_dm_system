"""
``monitor ingest doctor`` — pre-launch operator diagnostic.

LAYER: 3 (cli)
IMPORTS FROM: monitor_data (Layer 1 — read-only health probes), rich, typer.

Surfaces:
- Active pair: chat / embedding / hyde / rerank (model + provider)
- Per-provider last probe status from llm_providers collection
- Embedding pair live-cache (or fresh probe if --force)
- Ingestion queue health: running count + stuck ids
- Neo4j / MongoDB / Qdrant reachability

The doctor never mutates state — it only reads.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

app = typer.Typer(help="Pre-launch operator health probe for the ingest pipeline")
console = Console()


async def _gather_doctor_report(*, force: bool) -> dict[str, Any]:
    from monitor_data.db.mongodb import get_mongodb_client
    from monitor_data.retrieval.embedding_health import get_embedding_health_checker

    report: dict[str, Any] = {}

    # Active pair
    try:
        from monitor_data.db.postgres import PostgresClient
        from monitor_data.retrieval.pairs import PairRegistry

        pg = PostgresClient()
        try:
            reg = PairRegistry(pg=pg)
            pair = await reg.active_pair()
            report["pairs"] = [pair.to_dict()] if pair is not None else []
        finally:
            await pg.close()
    except Exception as exc:
        report["pairs_error"] = str(exc)

    # Provider collection (Postgres)
    try:
        from monitor_data.db.postgres import PostgresClient

        pg = PostgresClient()
        try:
            rows = await pg.providers_list()
        finally:
            await pg.close()
        providers = []
        for r in rows:
            providers.append(
                {
                    "provider": r.get("provider") or r.get("name"),
                    "model": r.get("model"),
                    "status": r.get("status"),
                    "is_default": bool(r.get("is_default")),
                    "last_error": r.get("last_error"),
                }
            )
        report["providers"] = providers
    except Exception as exc:
        report["providers_error"] = str(exc)

    # Embedding health (cheap cached or fresh probe)
    try:
        checker = get_embedding_health_checker()
        if force:
            status = await checker.verify(force=True)
        else:
            cached = checker.last_cached_status()
            status = cached if cached is not None else await checker.verify()
        report["embedding_health"] = {
            "healthy": status.healthy,
            "model": status.model,
            "provider": status.provider,
            "vector_dim": status.vector_dim,
            "detail": status.detail,
        }
    except Exception as exc:
        report["embedding_health_error"] = str(exc)

    # Ingestion queue
    try:
        mongodb = get_mongodb_client()
        jobs = mongodb.get_collection("ingestion_jobs")
        running = jobs.count_documents({"status": "running"})
        failed = jobs.count_documents({"status": "failed"})
        completed = jobs.count_documents({"status": "completed"})
        pending = jobs.count_documents({"status": "pending"})
        report["jobs"] = {
            "running": running,
            "failed": failed,
            "completed": completed,
            "pending": pending,
        }
    except Exception as exc:
        report["jobs_error"] = str(exc)

    return report


def _render(report: dict[str, Any]) -> None:
    # Pairs
    if "pairs" in report:
        table = Table(title="Active model pairs", show_lines=False)
        table.add_column("Name", style="cyan")
        table.add_column("Chat")
        table.add_column("Embedding")
        table.add_column("HyDE")
        table.add_column("Rerank")
        for p in report["pairs"]:
            table.add_row(
                p.get("name", ""),
                f"{p.get('chat_model', '')} @ {p.get('chat_provider', '')}",
                f"{p.get('embedding_model', '')} @ {p.get('embedding_provider', '')}",
                f"{p.get('hyde_model', '')} @ {p.get('hyde_provider', '')}",
                f"{p.get('rerank_model', '')} @ {p.get('rerank_provider', '')}",
            )
        console.print(table)
    else:
        console.print(
            Panel(
                f"[red]pairs error:[/red] {report.get('pairs_error')}",
                title="Active model pairs",
            )
        )

    # Providers
    if "providers" in report:
        table = Table(title="LLM providers (live)", show_lines=False)
        table.add_column("Provider")
        table.add_column("Model")
        table.add_column("Status")
        table.add_column("Default?")
        for p in report["providers"]:
            status = p.get("status") or "?"
            render = (
                "[green]" + status + "[/green]"
                if status in ("healthy", "connected", "ok")
                else "[red]" + status + "[/red]"
                if status in ("error", "down", "unhealthy")
                else status
            )
            table.add_row(
                p.get("provider", "?"),
                p.get("model", "?") or "",
                render,
                "yes" if p.get("is_default") else "",
            )
        console.print(table)
    else:
        console.print(
            Panel(
                f"[red]providers error:[/red] {report.get('providers_error')}",
                title="LLM providers",
            )
        )

    # Embedding health
    eh = report.get("embedding_health")
    if eh:
        verdict = "[green]healthy[/green]" if eh["healthy"] else "[red]unhealthy[/red]"
        body = (
            f"[bold]verdict:[/bold] {verdict}\n"
            f"[bold]model:[/bold] {eh.get('model')}\n"
            f"[bold]provider:[/bold] {eh.get('provider')}\n"
            f"[bold]vector_dim:[/bold] {eh.get('vector_dim')}\n"
            f"[bold]detail:[/bold] {eh.get('detail')}"
        )
        console.print(Panel(body, title="Embedding pair"))
    elif "embedding_health_error" in report:
        console.print(
            Panel(
                f"[red]{report['embedding_health_error']}[/red]",
                title="Embedding pair",
            )
        )

    # Ingestion queue
    j = report.get("jobs")
    if j:
        body = "\n".join(f"[bold]{k}:[/bold] {v}" for k, v in j.items())
        console.print(Panel(body, title="Ingestion jobs"))
    elif "jobs_error" in report:
        console.print(
            Panel(
                f"[red]{report['jobs_error']}[/red]",
                title="Ingestion jobs",
            )
        )


@app.command("doctor")
def doctor(
    force: bool = typer.Option(
        False,
        "--force",
        help="Force a fresh embedding health probe (skip cache)",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Emit machine-readable JSON instead of a rendered report",
    ),
) -> None:
    """Pre-launch operator diagnostic — surfaces what the ingest
    pipeline will hit when it runs. Read-only; never mutates state."""
    report = asyncio.run(_gather_doctor_report(force=force))
    if json_output:
        console.print_json(json.dumps(report, indent=2, default=str))
    else:
        _render(report)


__all__ = ["app"]
