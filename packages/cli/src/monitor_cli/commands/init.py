"""
``monitor init`` — first-run interactive wizard.

LAYER: 3 (cli)
IMPORTS FROM: monitor_agents (Layer 2 — health, wizard providers),
              questionary, rich, typer.

Brings a fresh checkout from "nothing running" to "ready to play" by:
  1. Pre-flight: verify docker infra is up; if not, print a clear
     "run `make infra-up`" message and exit nonzero.
  2. Schema bootstrap: idempotently reconnect Neo4j, Mongo, Postgres so
     constraints / indexes / DDL land before any provider work.
  3. Provider choice: a curated questionary menu (no keyword parsing).
  4. Branch on choice:
       - ollama: query /api/tags, pull missing model with rich progress,
         then seed ``ollama-local`` (role=light, default) and
         ``ollama-embedding`` (role=embedding, default).
       - anthropic / openai / github_models / google_ai_studio / minimax / zai:
         questionary.password for the API key, write to ``.env.tokens``
         (mode 0o600) for the cold-start fallback, then ``seed_provider``
         with the appropriate role default.
  5. Final: re-run health probe and render a green/red panel.

Strict menu — no free-form text parsing. Secrets never echoed, never logged.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import questionary
import typer
from monitor_agents.health import check_all_services
from monitor_agents.wizard import seed_provider
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

app = typer.Typer(
    name="init",
    help="First-run wizard: bring up providers and bootstrap the database schema.",
    no_args_is_help=True,
)
console = Console()


# ── secrets handling ─────────────────────────────────────────────────────────


ENV_TOKENS_PATH = Path(".env.tokens")


def _write_env_token(key: str, value: str, *, path: Path = ENV_TOKENS_PATH) -> None:
    """Write KEY=value to .env.tokens.

    Replaces the existing line if it is present, appends otherwise. Sets file
    mode 0o600 on first create so secrets are not world-readable.
    Never writes to /tmp. Never logs the value.
    """
    value = value.strip()
    if not value:
        return

    line = f"{key}={value}\n"
    existing_lines: list[str] = []
    new_file = not path.exists()
    if not new_file:
        existing_lines = path.read_text().splitlines()

    replaced = False
    new_lines: list[str] = []
    for raw in existing_lines:
        existing_key = raw.split("=", 1)[0].strip()
        if existing_key == key:
            if not replaced:
                new_lines.append(line.rstrip("\n"))
                replaced = True
            # else: drop the duplicate
        else:
            new_lines.append(raw)

    if not replaced:
        new_lines.append(line.rstrip("\n"))

    path.write_text("\n".join(new_lines) + "\n")
    if new_file:
        # Newly created — restrict so secrets are not world-readable.
        path.chmod(0o600)


# ── provider menu ────────────────────────────────────────────────────────────


# (id, label, env-var-name-for-secret, default-role-to-set)
PROVIDER_CHOICES = [
    questionary.Choice("Ollama (local-first, no API key)", value="ollama"),
    questionary.Choice("Anthropic Claude", value="anthropic"),
    questionary.Choice("OpenAI", value="openai"),
    questionary.Choice("GitHub Models", value="github_models"),
    questionary.Choice("Google AI Studio (Gemini)", value="google_ai_studio"),
    questionary.Choice("MiniMax AI", value="minimax"),
    questionary.Choice("Z.AI (ZhipuAI / GLM)", value="zai"),
]


# Default model + role per provider; keyed by provider id.
PROVIDER_DEFAULTS: dict[str, dict[str, Any]] = {
    "ollama": {
        "name": "Ollama (local)",
        "model": "qwen2.5:latest",
        "embedding_model": "nomic-embed-text:latest",
        "base_url": "http://localhost:11434/v1",
    },
    "anthropic": {
        "name": "Anthropic Claude",
        "model": "claude-sonnet-4-20250514",
        "api_key_env": "ANTHROPIC_API_KEY",
        "role": "heavy",
    },
    "openai": {
        "name": "OpenAI",
        "model": "gpt-4o-mini",
        "embedding_model": "text-embedding-3-small",
        "api_key_env": "OPENAI_API_KEY",
        "role": "standard",
    },
    "github_models": {
        "name": "GitHub Models",
        "model": "openai/gpt-4.1-mini",
        "api_key_env": "GITHUB_MODELS_TOKEN",
        "base_url": "https://models.github.ai/inference",
        "role": "standard",
    },
    "google_ai_studio": {
        "name": "Google AI Studio",
        "model": "gemini-2.5-flash",
        "api_key_env": "GOOGLE_API_KEY",
        "role": "heavy",
    },
    "minimax": {
        "name": "MiniMax AI",
        "model": "MiniMax/MiniMax-M2.7",
        "api_key_env": "MINIMAX_API_KEY",
        "role": "heavy",
    },
    "zai": {
        "name": "Z.AI (ZhipuAI)",
        "model": "glm-5.1",
        "api_key_env": "Z_AI_API_KEY",
        "base_url": "https://api.z.ai/api/coding/paas/v4",
        "role": "heavy",
    },
}


# ── pre-flight ───────────────────────────────────────────────────────────────


async def _preflight() -> dict[str, Any] | None:
    """Run the component health probe. Returns the report, or None on failure.

    Caller should print the actionable error message and ``raise typer.Exit(1)``
    when None is returned.
    """
    try:
        return await check_all_services()
    except Exception as exc:
        console.print(Panel(f"[red]{exc}[/red]", title="Health probe crashed"))
        return None


async def _bootstrap_schemas() -> None:
    """Re-connect each DB client so its idempotent bootstrap SQL runs."""
    from monitor_data.db.mongodb import get_mongodb_client
    from monitor_data.db.neo4j import get_neo4j_client
    from monitor_data.db.postgres import get_postgres_client

    console.print("[dim]Bootstrapping schemas (idempotent)…[/dim]")
    try:
        neo4j = get_neo4j_client()
        await neo4j.connect()
    except Exception as exc:
        console.print(f"   [yellow]![/yellow] Neo4j bootstrap skipped: {exc}")

    try:
        mongodb = get_mongodb_client()
        await mongodb.connect()
    except Exception as exc:
        console.print(f"   [yellow]![/yellow] MongoDB bootstrap skipped: {exc}")

    try:
        postgres = get_postgres_client()
        await postgres.connect()
    except Exception as exc:
        console.print(f"   [yellow]![/yellow] Postgres bootstrap skipped: {exc}")


# ── ollama branch ────────────────────────────────────────────────────────────


async def _ensure_ollama_model(model: str) -> bool:
    """Return True if the model is present locally; pull it if not.

    On failure (Ollama not installed, model pull errored, network down), print
    the actionable error and return False. The wizard will exit with a clear
    next-step.
    """
    if not shutil.which("ollama"):
        console.print(
            Panel(
                "Ollama is not on your PATH. Install it from https://ollama.com "
                "and re-run `monitor init --provider ollama`.",
                title="[red]Ollama missing[/red]",
            )
        )
        return False

    base = "http://localhost:11434"
    try:
        import urllib.request

        with urllib.request.urlopen(f"{base}/api/tags", timeout=5) as r:
            data = json.loads(r.read())
            installed = {m.get("name", "") for m in data.get("models", [])}
    except Exception as exc:
        console.print(
            Panel(
                f"Could not reach Ollama at {base}: {exc}\n\n"
                "Start the Ollama daemon (`ollama serve` or the desktop app) "
                "and re-run `monitor init --provider ollama`.",
                title="[red]Ollama unreachable[/red]",
            )
        )
        return False

    if model in installed:
        console.print(f"   [green]✔[/green] {model} already present")
        return True

    console.print(f"   pulling {model} (this can take a few minutes)…")
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}")) as progress:
        progress.add_task(f"ollama pull {model}", total=None)
        result = subprocess.run(
            ["ollama", "pull", model],
            capture_output=True,
            text=True,
            timeout=1800,
        )
    if result.returncode != 0:
        console.print(
            Panel(
                f"`ollama pull {model}` failed:\n{result.stderr.strip()}",
                title="[red]Ollama pull failed[/red]",
            )
        )
        return False
    return True


async def _seed_ollama() -> bool:
    cfg = PROVIDER_DEFAULTS["ollama"]
    chat_model = os.getenv("OLLAMA_MODEL", cfg["model"]).strip() or cfg["model"]
    embed_model = os.getenv("MONITOR_OLLAMA_EMBEDDING_MODEL", cfg["embedding_model"]).strip() or cfg["embedding_model"]

    if not await _ensure_ollama_model(chat_model):
        return False
    if not await _ensure_ollama_model(embed_model):
        return False

    await seed_provider(
        id="ollama-local",
        name=cfg["name"],
        provider_type="ollama",
        model=chat_model,
        role="light",
        base_url=cfg["base_url"],
        is_default=True,
        model_params={"temperature": 0.7, "max_tokens": 4096},
    )
    await seed_provider(
        id="ollama-embedding",
        name="Ollama Embedding",
        provider_type="ollama",
        model=embed_model,
        role="embedding",
        base_url=cfg["base_url"].replace("/v1", ""),
        is_default=True,
        model_params={},
    )
    return True


# ── BYOK branches ────────────────────────────────────────────────────────────


def _ask_for_key(env_var: str, *, required: bool = True, prefill: str | None = None) -> str | None:
    """Prompt for an API key using questionary.password (no echo).

    If ``prefill`` is supplied (e.g. an env-var value), it is returned without
    prompting — used for ``--yes`` mode when the key is already configured.
    """
    if prefill is not None and prefill.strip():
        return prefill.strip()

    prompt = f"Enter your {env_var}"
    if required:
        prompt += " (input is hidden)"
    while True:
        value: str | None = questionary.password(prompt).ask()
        if value is None:
            return None  # user cancelled
        value = value.strip()
        if value or not required:
            return value
        console.print("[yellow]API key cannot be empty — try again or Ctrl-C to abort.[/yellow]")


def _resolve_existing_key(env_var: str) -> str:
    """Look up an API key in ``.env.tokens`` or the process environment.

    Empty string if not set. Used by ``--yes`` mode so the wizard can run
    non-interactively when the user has already exported the key.
    """
    # .env.tokens is the canonical secrets file (mode 0o600); check it first.
    tokens_path = ENV_TOKENS_PATH
    if tokens_path.exists():
        for raw in tokens_path.read_text().splitlines():
            key, sep, val = raw.partition("=")
            if sep and key.strip() == env_var:
                return val.strip()
    # Process env is the fallback (set by `export ANTHROPIC_API_KEY=…` etc).
    return os.getenv(env_var, "").strip()


async def _seed_byok(provider_id: str, *, non_interactive: bool = False) -> bool:
    cfg = PROVIDER_DEFAULTS[provider_id]
    env_var = cfg["api_key_env"]

    # In non-interactive mode, require a pre-existing key; never prompt.
    prefill = _resolve_existing_key(env_var) if non_interactive else None
    if non_interactive and not prefill:
        console.print(
            Panel(
                f"--yes requires {env_var} to be set in .env.tokens or the "
                f"process environment before running `monitor init`. Either "
                f"export it (`export {env_var}=…`) or re-run without --yes.",
                title="[red]API key required[/red]",
            )
        )
        return False

    api_key = _ask_for_key(env_var, prefill=prefill)
    if not api_key:
        console.print("[yellow]aborted[/yellow]")
        return False

    # 1. Write to .env.tokens so the env-var fallback path is populated.
    _write_env_token(env_var, api_key)

    # 2. Seed the DB row with the appropriate role default.
    await seed_provider(
        id=f"{provider_id}-default",
        name=cfg["name"],
        provider_type=provider_id,
        model=cfg["model"],
        role=cfg["role"],
        api_key=api_key,
        base_url=cfg.get("base_url"),
        is_default=True,
    )
    console.print(f"   [green]✔[/green] seeded {cfg['name']} as default for role={cfg['role']!r}")

    # 3. For openai, also seed the embedding role if the user wants it.
    if provider_id == "openai":
        wants_embed = False
        if non_interactive:
            wants_embed = False  # safe default; user can rerun interactively
        else:
            wants_embed = bool(await questionary.confirm("Use OpenAI for embeddings too?", default=False).ask_async())
        if wants_embed:
            await seed_provider(
                id="openai-embedding-default",
                name="OpenAI Embedding",
                provider_type="openai",
                model=cfg["embedding_model"],
                role="embedding",
                api_key=api_key,
                is_default=True,
            )
            console.print("   [green]✔[/green] seeded OpenAI Embedding as default for role='embedding'")
    return True


# ── command ──────────────────────────────────────────────────────────────────


@app.callback(invoke_without_command=True)
def init(
    provider: str | None = typer.Option(
        None,
        "--provider",
        "-p",
        help="ollama | anthropic | openai | github_models | google_ai_studio | minimax | zai",
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print the wizard steps without writing anything."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip interactive prompts (use --provider)."),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """First-run wizard. Brings up providers and bootstraps the database schema.

    With no flags, runs the interactive questionary menu. With ``--provider
    <name> --yes``, skips prompts and runs straight to that branch (used by
    ``make test-e2e`` and the e2e harness).
    """
    if dry_run:
        plan = {
            "would_run": [
                "preflight: check_all_services()",
                "bootstrap: neo4j.connect(), mongodb.connect(), postgres.connect()",
                f"seed provider: {provider or '<menu choice>'}",
                "postflight: check_all_services() (assert healthy)",
            ],
            "would_write": [
                ".env.tokens (if BYOK provider)",
                "llm_providers row in Postgres",
            ],
        }
        # Use plain print() so subprocess capture / test runners get clean JSON.
        # Rich's console.print_json adds ANSI syntax highlighting that some
        # downstream consumers strip and re-emit, causing parse errors.
        print(json.dumps(plan, indent=2))
        return

    # 1. Pre-flight
    console.print(Panel("MONITOR first-run wizard", border_style="cyan"))
    report = asyncio.run(_preflight())
    if report is None:
        raise typer.Exit(code=1)

    overall = report.get("overall_status", "unknown")
    if overall == "unhealthy":
        console.print(
            Panel(
                "[red]Infra is unhealthy.[/red]\n\n"
                "Run `make infra-up` to start the database containers, then "
                "re-run `monitor init`. If you've already changed "
                "NEO4J_PASSWORD after a prior run, use `make infra-restart-volume` "
                "to wipe the stale volume.",
                title="Pre-flight failed",
            )
        )
        raise typer.Exit(code=1)

    if overall != "healthy":
        console.print(
            f"[yellow]Pre-flight reports '{overall}' — some services may not be "
            "reachable. The wizard will continue but the seeded providers may "
            "not be able to reach their backing services.[/yellow]"
        )

    # 2. Bootstrap schemas (idempotent)
    asyncio.run(_bootstrap_schemas())

    # 3. Provider choice
    if yes and provider:
        chosen = provider
    else:
        chosen = questionary.select(
            "Which provider do you want to use for MONITOR?",
            choices=PROVIDER_CHOICES,
        ).ask()
        if chosen is None:
            console.print("[yellow]aborted[/yellow]")
            raise typer.Exit(code=130)

    if chosen not in PROVIDER_DEFAULTS:
        console.print(f"[red]unknown provider: {chosen}[/red]")
        raise typer.Exit(code=2)

    # 4. Branch
    if chosen == "ollama":
        ok = asyncio.run(_seed_ollama())
    else:
        ok = asyncio.run(_seed_byok(chosen, non_interactive=yes))

    if not ok:
        raise typer.Exit(code=1)

    # 5. Post-flight
    console.print()
    final = asyncio.run(check_all_services())
    final_overall = final.get("overall_status", "unknown")
    summary_style = "green" if final_overall == "healthy" else "yellow" if final_overall == "degraded" else "red"
    console.print(
        Panel(
            f"[bold {summary_style}]{final_overall}[/bold {summary_style}]\n\n"
            "You're ready to play. Run:\n"
            '  uv run python -m monitor_cli.main play --story "My Campaign"',
            title="Init complete",
            border_style=summary_style,
        )
    )

    if json_output:
        out = {
            "provider": chosen,
            "preflight": overall,
            "postflight": final_overall,
            "components": final.get("components", {}),
        }
        print(json.dumps(out, indent=2, default=str))

    if final_overall == "unhealthy":
        raise typer.Exit(code=1)


__all__ = ["app"]
