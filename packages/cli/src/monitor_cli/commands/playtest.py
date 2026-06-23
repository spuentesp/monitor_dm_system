"""Live playtest commands for MONITOR system testing.

LAYER: 3 (cli)
IMPORTS FROM: external libraries only + stdlib subprocess wrapper
NEVER IMPORTS: monitor_data directly
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel

app = typer.Typer(help="Run live autonomous-GM playtests and capture gameplay logs")
console = Console()


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[5]


def _run_playtest(
    *,
    api_url: str,
    player_mode: str,
    turns: int,
    runs: int,
    output_dir: Path,
    benchmark_id: str | None,
) -> None:
    repo_root = _repo_root()
    script_path = repo_root / "scripts" / "live_gameplay_smoke.py"
    if not script_path.exists():
        raise typer.Exit(code=2)

    output_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        str(script_path),
        "--api-url",
        api_url,
        "--player-mode",
        player_mode,
        "--turns",
        str(turns),
        "--runs",
        str(runs),
        "--output-dir",
        str(output_dir),
    ]
    if benchmark_id:
        cmd.extend(["--benchmark-id", benchmark_id])

    console.print(
        Panel.fit(
            f"[bold]Running playtest[/bold]\n"
            f"API: {api_url}\n"
            f"Player: {player_mode}\n"
            f"Benchmark: {benchmark_id or 'default'}\n"
            f"Runs: {runs}\n"
            f"Turns per run: {turns}",
            title="MONITOR Playtest",
        )
    )
    result = subprocess.run(
        cmd,
        cwd=repo_root,
        capture_output=True,
        text=True,
        timeout=max(600, runs * turns * 90),
        check=False,
    )

    if result.stdout.strip():
        console.print(result.stdout)
    if result.stderr.strip():
        console.print(f"[yellow]{result.stderr}[/yellow]")

    if result.returncode != 0:
        raise typer.Exit(code=result.returncode)


@app.command("live")
def live(
    api_url: str = typer.Option(
        os.environ.get("MONITOR_API_URL", "http://localhost:8001/api"), help="Live backend API URL"
    ),
    player_mode: str = typer.Option(
        "scripted",
        "--player",
        help="Player driver: scripted, llm, or adversarial_llm",
        case_sensitive=False,
    ),
    benchmark_id: str = typer.Option(
        "narrative_weighted_derelict",
        "--benchmark",
        help="Configured benchmark flow to run",
    ),
    turns: int = typer.Option(6, min=1, max=20, help="Number of player turns to run"),
    runs: int = typer.Option(1, min=1, max=20, help="Number of sessions to run"),
    output_dir: Path = typer.Option(
        Path("tests/e2e/logs"),
        help="Directory where gameplay logs will be written",
    ),
) -> None:
    """Run a live playtest against the active backend and save a gameplay log."""
    _run_playtest(
        api_url=api_url,
        player_mode=player_mode,
        turns=turns,
        runs=runs,
        output_dir=output_dir,
        benchmark_id=benchmark_id,
    )


@app.command("compare")
def compare(
    api_url: str = typer.Option(
        os.environ.get("MONITOR_API_URL", "http://localhost:8001/api"), help="Live backend API URL"
    ),
    player_mode: str = typer.Option(
        "adversarial_llm",
        "--player",
        help="Player driver for comparison runs: scripted, llm, or adversarial_llm",
        case_sensitive=False,
    ),
    benchmark_id: str = typer.Option(
        "death_in_space_onboarding_probe",
        "--benchmark",
        help="Configured benchmark flow to compare across runs",
    ),
    turns: int = typer.Option(6, min=1, max=20, help="Number of player turns per run"),
    runs: int = typer.Option(3, min=2, max=20, help="Number of sessions to compare"),
    output_dir: Path = typer.Option(
        Path("tests/e2e/logs"),
        help="Directory where gameplay logs will be written",
    ),
) -> None:
    """Run multiple live playtests for loop comparison and regression hunting."""
    _run_playtest(
        api_url=api_url,
        player_mode=player_mode,
        turns=turns,
        runs=runs,
        output_dir=output_dir,
        benchmark_id=benchmark_id,
    )
