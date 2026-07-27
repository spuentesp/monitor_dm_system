"""
``monitor doctor`` — system-wide operator diagnostic + idempotent repair.

LAYER: 3 (cli)
IMPORTS FROM: monitor_agents (Layer 2 — health aggregator, repair helpers),
              monitor_cli.commands.ingest_doctor (Layer 3 — ingest pipeline view).

This is the operator entry point for "is MONITOR healthy and ready to play?"
Distinct from ``monitor ingest-doctor`` (which is scoped to the ingest
pipeline). The two surfaces share naming intentionally: ``doctor`` is the
whole-system check, ``ingest-doctor`` is the pipeline-specific one.

What ``doctor`` reports (read-only):
- Component reachability: neo4j, mongodb, qdrant, postgres, minio, llm.
- Per-component status from ``monitor_agents.health.check_all_services``.
- Ingest pipeline view: active pairs, llm_providers rows, embedding health,
  ingestion job counts — re-uses ``ingest_doctor._gather_doctor_report``.

What ``--fix`` does (idempotent):
- Re-applies DB schemas by calling each client's ``connect()`` (idempotent).
- Re-creates Qdrant collections listed in ``COLLECTION_CONFIGS``.
- Re-ensures the MinIO bucket.
- Re-seeds default LLM providers if ``llm_providers`` is empty.
- Re-pulls Ollama models if missing locally.
- Each step prints progress; failures are surfaced per-step, never fatal.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import typer
from monitor_agents.health import check_all_services
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from monitor_cli.commands.ingest_doctor import _gather_doctor_report

app = typer.Typer(
    name="doctor",
    help="System-wide health check + idempotent repair (see also `monitor ingest-doctor`).",
    no_args_is_help=True,
)
console = Console()


# ── rendering helpers ────────────────────────────────────────────────────────


def _status_render(status: str) -> str:
    s = status or "unknown"
    if s in ("healthy", "connected", "ok"):
        return f"[green]{s}[/green]"
    if s in ("degraded",):
        return f"[yellow]{s}[/yellow]"
    if s in ("error", "unhealthy", "down"):
        return f"[red]{s}[/red]"
    return s


def _render_component_table(components: dict[str, dict[str, Any]]) -> None:
    table = Table(title="Components", show_lines=False)
    table.add_column("Component", style="cyan")
    table.add_column("Status")
    table.add_column("Detail")
    for name, payload in components.items():
        status = payload.get("status", "?")
        detail = payload.get("message") or payload.get("detail") or ""
        table.add_row(name, _status_render(status), detail)
    console.print(table)


def _render_ingest_section(ingest_report: dict[str, Any]) -> None:
    """Render the ingest-pipeline view inline. Reuses ingest_doctor's data shape."""
    # Pairs
    pairs = ingest_report.get("pairs") or []
    if pairs:
        rows = "\n".join(
            f"  • {p.get('name', '')}: chat={p.get('chat_model')} embed={p.get('embedding_model')}" for p in pairs
        )
        console.print(Panel(rows, title="Active model pairs"))
    elif "pairs_error" in ingest_report:
        console.print(Panel(f"[red]{ingest_report['pairs_error']}[/red]", title="Active model pairs"))

    # Providers
    providers = ingest_report.get("providers") or []
    if providers:
        rows = "\n".join(
            f"  • {p.get('provider', '?')}/{p.get('model', '?')} "
            f"[{_status_render(p.get('status') or '?')}]"
            f"{' (default)' if p.get('is_default') else ''}"
            for p in providers
        )
        console.print(Panel(rows or "  (none)", title="LLM providers"))
    elif "providers_error" in ingest_report:
        console.print(Panel(f"[red]{ingest_report['providers_error']}[/red]", title="LLM providers"))

    # Embedding health
    eh = ingest_report.get("embedding_health")
    if eh:
        verdict = "[green]healthy[/green]" if eh.get("healthy") else "[red]unhealthy[/red]"
        body = f"verdict: {verdict}\nmodel:   {eh.get('model')}\ndim:     {eh.get('vector_dim')}"
        console.print(Panel(body, title="Embedding pair"))
    elif "embedding_health_error" in ingest_report:
        console.print(Panel(f"[red]{ingest_report['embedding_health_error']}[/red]", title="Embedding pair"))

    # Jobs
    jobs = ingest_report.get("jobs")
    if jobs:
        body = "\n".join(f"  {k}: {v}" for k, v in jobs.items())
        console.print(Panel(body, title="Ingestion jobs"))
    elif "jobs_error" in ingest_report:
        console.print(Panel(f"[red]{ingest_report['jobs_error']}[/red]", title="Ingestion jobs"))


# ── --fix repair steps (idempotent, no keyword parsing) ───────────────────────


async def _fix_dbs() -> dict[str, str]:
    """Re-apply schema bootstrap by calling each client's connect().

    Each connect() is idempotent (CREATE CONSTRAINT … IF NOT EXISTS,
    CREATE INDEX … IF NOT EXISTS, _SCHEMA_SQL on Postgres). Returns a
    per-component verdict dict.
    """
    verdicts: dict[str, str] = {}

    try:
        from monitor_data.db.neo4j import get_neo4j_client

        neo4j_client = get_neo4j_client()
        await neo4j_client.connect()
        verdicts["neo4j"] = "ok"
    except Exception as exc:
        verdicts["neo4j"] = f"error: {exc}"

    try:
        from monitor_data.db.mongodb import get_mongodb_client

        mongodb_client = get_mongodb_client()
        await mongodb_client.connect()
        verdicts["mongodb"] = "ok"
    except Exception as exc:
        verdicts["mongodb"] = f"error: {exc}"

    try:
        from monitor_data.db.postgres import get_postgres_client

        pg_client = get_postgres_client()
        await pg_client.connect()
        verdicts["postgres"] = "ok"
    except Exception as exc:
        verdicts["postgres"] = f"error: {exc}"

    try:
        from monitor_data.db.qdrant import COLLECTION_CONFIGS, get_qdrant_client

        qdrant_client = get_qdrant_client()
        for name in COLLECTION_CONFIGS:
            try:
                qdrant_client.ensure_collection(name)
            except Exception as exc:
                verdicts[f"qdrant:{name}"] = f"error: {exc}"
        verdicts["qdrant"] = "ok"
    except Exception as exc:
        verdicts["qdrant"] = f"error: {exc}"

    try:
        from monitor_data.db.minio import get_minio_client

        minio_client = get_minio_client()
        await minio_client.ensure_bucket()
        verdicts["minio"] = "ok"
    except Exception as exc:
        verdicts["minio"] = f"error: {exc}"

    return verdicts


def _fix_providers_if_empty() -> str:
    """Re-seed default LLM providers only when llm_providers is empty.

    Idempotent: only runs when the table has zero rows; safe to invoke on
    a healthy system (no-op).
    """
    try:
        from monitor_data.db.postgres import get_postgres_client

        async def _check_and_seed() -> str:
            client = get_postgres_client()
            try:
                rows = await client.providers_list()
            finally:
                await client.close()
            if rows:
                return f"skipped ({len(rows)} existing rows)"
            # Empty — run the seeder as a subprocess (it parses .env + creates defaults).
            seed_script = Path("scripts/seed_llm_providers.py")
            if not seed_script.exists():
                return "skipped (no seed script)"
            result = subprocess.run(
                ["uv", "run", "python", str(seed_script)],
                capture_output=True,
                text=True,
                timeout=60,
            )
            return "ok" if result.returncode == 0 else f"error: {result.stderr.strip()}"

        return asyncio.run(_check_and_seed())
    except Exception as exc:
        return f"error: {exc}"


def _fix_ollama_models() -> str:
    """Re-pull Ollama models if missing.

    Checks the local ``ollama list`` output; if ``nomic-embed-text`` is
    absent, runs ``ollama pull nomic-embed-text`` and shows progress via
    a streaming subprocess call.
    """
    if not shutil.which("ollama"):
        return "skipped (ollama not on PATH)"

    try:
        list_result = subprocess.run(
            ["ollama", "list"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if list_result.returncode != 0:
            return f"error: ollama list failed: {list_result.stderr.strip()}"

        have_models = list_result.stdout
        needed = ["nomic-embed-text", "llama3.2"]
        missing = [m for m in needed if m not in have_models]
        if not missing:
            return "ok (all default models present)"

        console.print(f"   pulling missing models: {missing}")
        for model in missing:
            with console.status(f"[cyan]pulling {model}…[/cyan]"):
                result = subprocess.run(
                    ["ollama", "pull", model],
                    capture_output=True,
                    text=True,
                    timeout=600,
                )
                if result.returncode != 0:
                    return f"error pulling {model}: {result.stderr.strip()}"
        return "ok"
    except subprocess.TimeoutExpired:
        return "error: ollama pull timed out"
    except Exception as exc:
        return f"error: {exc}"


# ── command ───────────────────────────────────────────────────────────────────


@app.callback(invoke_without_command=True)
def doctor(
    ctx: typer.Context,
    fix: bool = typer.Option(False, "--fix", help="Run idempotent repair after the report."),
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
    force: bool = typer.Option(False, "--force", help="Bypass embedder health cache."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip --fix confirmation prompt."),
) -> None:
    """System-wide health check + idempotent repair.

    Read-only by default. With ``--fix``, runs a strict menu of idempotent
    repair steps (re-apply DB schemas, re-create Qdrant collections, ensure
    MinIO bucket, re-seed providers if empty, re-pull Ollama models). Each
    step is logged; no step silently mutates state.
    """
    # Run both reports. Sequential — `asyncio.run` accepts a coroutine, not
    # an arbitrary awaitable, and the wall-clock difference is tiny for two
    # HTTP-shaped probes against localhost services.
    components_report: dict[str, Any] = asyncio.run(check_all_services(force=force))
    ingest_report: dict[str, Any] = asyncio.run(_gather_doctor_report(force=force))

    overall = components_report.get("overall_status", "unknown")
    fix_verdicts: dict[str, Any] | None = None

    if fix:
        # Print a red "Will run repair:" panel and gate on typer.confirm.
        steps = [
            "1. Re-apply DB schemas (Neo4j constraints, Mongo indexes, Postgres DDL)",
            "2. Re-create Qdrant collections (scenes, memories, snippets, entities, knowledge)",
            "3. Ensure MinIO bucket exists",
            "4. Re-seed default LLM providers if llm_providers is empty",
            "5. Re-pull Ollama models (nomic-embed-text, llama3.2) if missing",
        ]
        console.print(
            Panel(
                "\n".join(steps),
                title="[bold red]Will run repair[/bold red]",
                border_style="red",
            )
        )
        if not yes and not typer.confirm("Proceed?", default=False):
            console.print("[yellow]aborted[/yellow]")
            raise typer.Exit(code=130)

        db_verdicts = asyncio.run(_fix_dbs())
        providers_verdict = _fix_providers_if_empty()
        ollama_verdict = _fix_ollama_models()
        fix_verdicts = {
            "dbs": db_verdicts,
            "providers": providers_verdict,
            "ollama": ollama_verdict,
        }

    # Re-run component health after repair so the user sees the deltas.
    if fix:
        components_report = asyncio.run(check_all_services(force=True))
        overall = components_report.get("overall_status", "unknown")

    if json_output:
        out = {
            "overall_status": overall,
            "components": components_report.get("components", {}),
            "ingest": ingest_report,
            "fix": fix_verdicts,
        }
        # Plain print() so subprocess capture gets clean JSON. Rich's
        # console.print_json would add ANSI syntax-highlighting codes.
        print(json.dumps(out, indent=2, default=str))
        # Exit non-zero if unhealthy so CI / scripts can branch on it.
        if overall == "unhealthy":
            raise typer.Exit(code=1)
        return

    # Visual mode
    _render_component_table(components_report.get("components", {}))
    console.print()
    _render_ingest_section(ingest_report)

    if fix_verdicts:
        console.print()
        console.print(Panel(_format_fix_verdicts(fix_verdicts), title="Repair results"))

    summary_style = "green" if overall == "healthy" else "yellow" if overall == "degraded" else "red"
    console.print()
    console.print(
        Panel(
            f"[bold {summary_style}]{overall}[/bold {summary_style}]",
            title="Overall",
            border_style=summary_style,
        )
    )

    if overall == "unhealthy":
        raise typer.Exit(code=1)


def _format_fix_verdicts(verdicts: dict[str, Any]) -> str:
    lines: list[str] = []
    for key, val in verdicts.items():
        if isinstance(val, dict):
            lines.append(f"[bold]{key}[/bold]:")
            for k, v in val.items():
                lines.append(f"  • {k}: {_status_render(v)}")
        else:
            lines.append(f"[bold]{key}[/bold]: {_status_render(val)}")
    return "\n".join(lines)


__all__ = ["app"]
