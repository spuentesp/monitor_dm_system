"""
Seed the llm_providers table with GitHub Models, Google AI Studio, and Ollama.

Credentials are read from environment variables — matching pii_chan's resolution
order so both projects use the same tokens.

  GitHub Models  : GITHUB_MODELS_TOKEN → GITHUB_TOKEN → GH_TOKEN
  Google AI Studio: GOOGLE_API_KEY
  Ollama          : no key required

Usage (from repo root, with .env loaded):
    python scripts/seed_llm_providers.py

The script is idempotent — it uses ON CONFLICT upsert, so re-running is safe.
Pass --dry-run to print the rows that would be inserted without touching the DB.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

# Make monitor_data importable from the repo root
sys.path.insert(0, "packages/data-layer/src")


def _resolve_github_token() -> str:
    for var in ("GITHUB_MODELS_TOKEN", "GITHUB_TOKEN", "GH_TOKEN"):
        value = os.getenv(var, "").strip()
        if value:
            return value
    return ""


def _resolve_google_key() -> str:
    return os.getenv("GOOGLE_API_KEY", "").strip()


def _resolve_ollama_base_url() -> str:
    return os.getenv("OLLAMA_ENDPOINT", "http://localhost:11434").rstrip("/") + "/v1"


def _discover_ollama_model(base_url: str) -> str:
    """Query Ollama /api/tags and return the first installed model name, or fall back to env/default."""
    env_model = os.getenv("OLLAMA_MODEL", "").strip()
    if env_model:
        return env_model
    try:
        import urllib.request

        ol_base = base_url.replace("/v1", "")
        with urllib.request.urlopen(f"{ol_base}/api/tags", timeout=5) as r:
            import json as _json

            data = _json.loads(r.read())
            models = [m["name"] for m in data.get("models", []) if m.get("name")]
            if models:
                print(f"  [ollama] auto-discovered models: {models}")
                return models[0]
    except Exception as exc:
        print(f"  [ollama] model discovery failed: {exc} — using default")
    return "llama3"


def _providers() -> list[dict]:
    github_model = os.getenv("GITHUB_MODELS_MODEL", "openai/gpt-4.1-mini").strip()
    google_model = os.getenv("GOOGLE_MODEL", "gemini-2.5-flash").strip()
    ol_base_url = _resolve_ollama_base_url()
    ollama_model = _discover_ollama_model(ol_base_url)

    return [
        {
            "id": "github-models-default",
            "name": "GitHub Models",
            "provider": "github_models",
            "model": github_model,
            "api_key": _resolve_github_token(),
            "base_url": os.getenv(
                "GITHUB_MODELS_BASE_URL", "https://models.github.ai/inference"
            ),
            "model_params": {"temperature": 0.7, "max_tokens": 4096},
            "role": "standard",
            "is_default": False,
        },
        {
            "id": "google-ai-studio-default",
            "name": "Google AI Studio",
            "provider": "google_ai_studio",
            "model": google_model,
            "api_key": _resolve_google_key(),
            # base_url is the well-known one already in PROVIDER_BASE_URLS
            "base_url": None,
            "model_params": {"temperature": 0.7, "max_tokens": 8192},
            "role": "heavy",
            "is_default": False,
        },
        {
            "id": "ollama-local",
            "name": "Ollama (local)",
            "provider": "ollama",
            "model": ollama_model,
            "api_key": "",
            "base_url": ol_base_url,
            "model_params": {"temperature": 0.7, "max_tokens": 4096},
            "role": "light",
            "is_default": False,
        },
    ]


async def _seed(dry_run: bool = False) -> None:
    providers = _providers()

    if dry_run:
        print("DRY RUN — providers that would be upserted:")
        for p in providers:
            display = dict(p)
            if display.get("api_key"):
                display["api_key"] = display["api_key"][:8] + "…"
            print(json.dumps(display, indent=2))
        return

    from monitor_data.db.postgres import PostgresClient  # noqa: PLC0415

    postgres = PostgresClient()
    try:
        await postgres.connect()
        for p in providers:
            await postgres.provider_upsert(p)
            key_hint = "(from env)" if p["api_key"] else "(no key)"
            print(f"  ✓ upserted: {p['id']} [{p['role']}] {key_hint}")
    finally:
        await postgres.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print provider rows without writing to the database",
    )
    args = parser.parse_args()

    # Load .env if present
    env_file = os.path.join(os.path.dirname(__file__), "..", ".env")
    if os.path.exists(env_file):
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, val = line.partition("=")
                    os.environ.setdefault(key.strip(), val.strip())

    asyncio.run(_seed(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
