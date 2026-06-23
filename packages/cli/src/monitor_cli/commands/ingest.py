"""
Ingest Command — document ingestion CLI for MONITOR.

LAYER: 3 (cli)
IMPORTS FROM: monitor_agents (Layer 2) only
NEVER IMPORTS: monitor_data (Layer 1)

Commands:
    $ monitor ingest file <path>   Ingest a local file (PDF/EPUB/MD/TXT/DOCX)
    $ monitor ingest uri <url>     Ingest a web page or remote document
    $ monitor ingest status <id>   Show ingestion job status
"""

import asyncio
from pathlib import Path
from typing import Optional
from uuid import UUID

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

app = typer.Typer(help="Ingest documents into the world knowledge base")
console = Console()

# Supported file extensions
SUPPORTED_EXTENSIONS = {".pdf", ".epub", ".md", ".txt", ".docx", ".html", ".htm"}


@app.command("file")
def ingest_file(
    path: Path = typer.Argument(..., help="Path to the file to ingest"),
    universe_id: UUID = typer.Option(..., "--universe", "-u", help="Target universe ID"),
    title: Optional[str] = typer.Option(
        None, "--title", "-t", help="Source title (default: filename)"
    ),
    pack_name: Optional[str] = typer.Option(
        None, "--pack", "-p", help="KnowledgePack name (default: source title)"
    ),
    pack_type: str = typer.Option(
        "setting_supplement",
        "--type",
        help="Pack type: rulebook, setting_supplement, adventure_module, homebrew, session_notes, wiki, custom",
    ),
    auto_apply: bool = typer.Option(
        False, "--auto-apply", help="Auto-create ProposedChanges after analysis"
    ),
    multiverse_id: Optional[UUID] = typer.Option(
        None, "--multiverse", "-m", help="Multiverse ID for auto-apply"
    ),
) -> None:
    """
    Ingest a local document file into the world knowledge base.

    The pipeline: upload → index (Qdrant) → analyze → KnowledgePack.
    After ingestion, CanonKeeper must evaluate the KnowledgePack to
    create entities, axioms, and lore facts in Neo4j.

    Examples:

        # Ingest a PDF rulebook
        monitor ingest file phb.pdf --universe <uuid> --type rulebook --title "D&D 5e PHB"

        # Ingest a setting supplement with auto-apply
        monitor ingest file lore.pdf --universe <uuid> --auto-apply --multiverse <uuid>
    """
    if not path.exists():
        console.print(f"[red]Error:[/red] File not found: {path}")
        raise typer.Exit(1)

    ext = path.suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        console.print(f"[red]Error:[/red] Unsupported file type: {ext}")
        console.print(f"Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}")
        raise typer.Exit(1)

    source_title = title or path.stem
    knowledge_pack_name = pack_name or source_title

    console.print(
        Panel(
            f"[bold]File:[/bold] {path}\n"
            f"[bold]Universe:[/bold] {universe_id}\n"
            f"[bold]Source title:[/bold] {source_title}\n"
            f"[bold]Pack name:[/bold] {knowledge_pack_name}\n"
            f"[bold]Pack type:[/bold] {pack_type}\n"
            f"[bold]Auto-apply:[/bold] {auto_apply}",
            title="[bold blue]Ingestion Pipeline",
            expand=False,
        )
    )

    file_bytes = path.read_bytes()
    asyncio.run(
        _run_ingest_file(
            file_bytes=file_bytes,
            filename=path.name,
            source_title=source_title,
            universe_id=universe_id,
            pack_name=knowledge_pack_name,
            pack_type=pack_type,
            auto_apply=auto_apply,
            multiverse_id=multiverse_id,
        )
    )


@app.command("uri")
def ingest_uri(
    url: str = typer.Argument(..., help="URL to fetch and ingest"),
    universe_id: UUID = typer.Option(..., "--universe", "-u", help="Target universe ID"),
    title: Optional[str] = typer.Option(None, "--title", "-t", help="Source title (default: URL)"),
    pack_name: Optional[str] = typer.Option(None, "--pack", "-p", help="KnowledgePack name"),
    pack_type: str = typer.Option("wiki", "--type", help="Pack type (default: wiki)"),
    auto_apply: bool = typer.Option(False, "--auto-apply", help="Auto-create ProposedChanges"),
    multiverse_id: Optional[UUID] = typer.Option(
        None, "--multiverse", "-m", help="Multiverse ID for auto-apply"
    ),
) -> None:
    """
    Fetch a URL and ingest its content into the world knowledge base.

    Example:

        monitor ingest uri https://example.com/lore --universe <uuid> --title "World Lore"
    """
    source_title = title or url
    knowledge_pack_name = pack_name or source_title

    console.print(
        Panel(
            f"[bold]URL:[/bold] {url}\n"
            f"[bold]Universe:[/bold] {universe_id}\n"
            f"[bold]Source title:[/bold] {source_title}",
            title="[bold blue]URI Ingestion Pipeline",
            expand=False,
        )
    )

    asyncio.run(
        _run_ingest_uri(
            uri=url,
            source_title=source_title,
            universe_id=universe_id,
            pack_name=knowledge_pack_name,
            pack_type=pack_type,
            auto_apply=auto_apply,
            multiverse_id=multiverse_id,
        )
    )


@app.command("status")
def ingest_status(
    job_id: UUID = typer.Argument(..., help="Ingestion job UUID"),
) -> None:
    """Show the current status of an ingestion job."""
    from monitor_agents.ingestion_pipeline import IngestionPipeline

    pipeline = IngestionPipeline()
    job = pipeline.get_job(job_id)
    if not job:
        console.print(f"[red]Job {job_id} not found.[/red]")
        raise typer.Exit(1)

    table = Table(title=f"Ingestion Job {job_id}", show_header=False)
    table.add_column("Field", style="bold")
    table.add_column("Value")

    table.add_row(
        "Status",
        f"[{'green' if str(job.status) == 'completed' else 'yellow'}]{job.status}[/]",
    )
    table.add_row("Stage", str(job.current_stage or "—"))
    table.add_row("Progress", f"{int((job.progress or 0) * 100)}%")
    table.add_row("Snippets", str(job.snippet_count))
    table.add_row("Entities extracted", str(job.entities_extracted))
    table.add_row("Axioms extracted", str(job.axioms_extracted))
    table.add_row("Errors", str(job.errors))
    console.print(table)


@app.command("apply")
def apply_pack(
    pack_id: UUID = typer.Argument(..., help="KnowledgePack UUID to apply"),
    multiverse_id: UUID = typer.Option(..., "--multiverse", "-m", help="Target multiverse"),
    universe_id: Optional[UUID] = typer.Option(
        None, "--universe", "-u", help="Optional universe scope"
    ),
    conflict: str = typer.Option(
        "merge", "--conflict", help="Conflict resolution: merge | skip | force"
    ),
    axioms: bool = typer.Option(True, help="Include axioms in proposals"),
    entities: bool = typer.Option(True, help="Include entities in proposals"),
    lore: bool = typer.Option(True, help="Include lore facts in proposals"),
) -> None:
    """
    Apply a KnowledgePack — create ProposedChanges for CanonKeeper evaluation.

    After running this command, invoke CanonKeeper to evaluate and commit
    the proposals to Neo4j (creating entities, axioms, lore facts).

    Example:

        monitor ingest apply <pack-id> --multiverse <uuid>
    """
    from monitor_agents.ingestion_pipeline import IngestionPipeline

    pipeline = IngestionPipeline()

    with Progress(
        SpinnerColumn(), TextColumn("[progress.description]{task.description}"), transient=True
    ) as progress:
        progress.add_task(f"Applying pack {pack_id}…")
        result = pipeline.apply_pack(
            pack_id,
            multiverse_id=multiverse_id,
            universe_id=universe_id,
            conflict_resolution=conflict,
            apply_axioms=axioms,
            apply_entities=entities,
            apply_lore_facts=lore,
            proposer="CLI",
        )

    console.print(
        Panel(
            f"[bold]Pack:[/bold] {pack_id}\n"
            f"[bold]Proposals created:[/bold] {result.get('proposals_created', 0)}\n"
            f"[bold]Axioms:[/bold] {result.get('axioms_proposed', 0)}\n"
            f"[bold]Entities:[/bold] {result.get('entities_proposed', 0)}\n"
            f"[bold]Lore facts:[/bold] {result.get('lore_facts_proposed', 0)}\n\n"
            "[dim]Run CanonKeeper to evaluate and commit to Neo4j.[/dim]",
            title="[bold green]KnowledgePack Applied",
            expand=False,
        )
    )


# =============================================================================
# Private async runners
# =============================================================================


async def _run_ingest_file(
    *,
    file_bytes: bytes,
    filename: str,
    source_title: str,
    universe_id: UUID,
    pack_name: str,
    pack_type: str,
    auto_apply: bool,
    multiverse_id: Optional[UUID],
) -> None:
    from monitor_agents.ingestion_pipeline import IngestionPipeline

    pipeline = IngestionPipeline()

    with Progress(
        SpinnerColumn(), TextColumn("[progress.description]{task.description}")
    ) as progress:
        task = progress.add_task("Stage 1/6 — Uploading to MinIO…")

        try:
            job = await pipeline.ingest_file(
                file_bytes=file_bytes,
                filename=filename,
                source_title=source_title,
                universe_id=universe_id,
                pack_name=pack_name,
                pack_type=pack_type,
                multiverse_id=multiverse_id,
                auto_apply=auto_apply,
            )
            progress.update(task, description="[green]Done!")
        except Exception as exc:
            progress.update(task, description=f"[red]Failed: {exc}")
            console.print(f"\n[red]Ingestion failed:[/red] {exc}")
            raise typer.Exit(1) from exc

    console.print(
        Panel(
            f"[bold]Job ID:[/bold] {job.job_id}\n"
            f"[bold]Status:[/bold] [green]{job.status}[/green]\n"
            f"[bold]Snippets indexed:[/bold] {job.snippet_count}\n"
            f"[bold]Pack name:[/bold] {pack_name}\n\n"
            "[dim]Review the KnowledgePack, then run:[/dim]\n"
            f"  monitor ingest apply <pack-id> --multiverse <uuid>",
            title="[bold green]Ingestion Complete",
            expand=False,
        )
    )


async def _run_ingest_uri(
    *,
    uri: str,
    source_title: str,
    universe_id: UUID,
    pack_name: str,
    pack_type: str,
    auto_apply: bool,
    multiverse_id: Optional[UUID],
) -> None:
    from monitor_agents.ingestion_pipeline import IngestionPipeline

    pipeline = IngestionPipeline()

    with Progress(
        SpinnerColumn(), TextColumn("[progress.description]{task.description}")
    ) as progress:
        task = progress.add_task("Fetching URI and ingesting…")
        try:
            job = await pipeline.ingest_uri(
                uri=uri,
                source_title=source_title,
                universe_id=universe_id,
                pack_name=pack_name,
                pack_type=pack_type,
                multiverse_id=multiverse_id,
                auto_apply=auto_apply,
            )
            progress.update(task, description="[green]Done!")
        except Exception as exc:
            progress.update(task, description=f"[red]Failed: {exc}")
            console.print(f"\n[red]Ingestion failed:[/red] {exc}")
            raise typer.Exit(1) from exc

    console.print(
        Panel(
            f"[bold]Job ID:[/bold] {job.job_id}\n"
            f"[bold]Status:[/bold] [green]{job.status}[/green]\n"
            f"[bold]Snippets:[/bold] {job.snippet_count}",
            title="[bold green]URI Ingestion Complete",
            expand=False,
        )
    )
