"""
Seed the llm_providers table with Z.AI (ZhipuAI) provider.

Z.AI is OpenAI-compatible and uses the standard OpenAI client with a custom base_url.

Credentials are read from environment variables:

  Z.AI API Key  : Z_AI_API_KEY
  Model          : Z_AI_MODEL (default: glm-5.1)
  Base URL       : Z_AI_BASE_URL (default: https://api.z.ai/api/coding/paas/v4)

Usage (from repo root, with .env loaded):
    python scripts/seed_zai_providers.py

The script is idempotent — it uses ON CONFLICT upsert, so re-running is safe.
Pass --dry-run to print the row that would be inserted without touching the DB.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

# Make monitor_data importable from the repo root
sys.path.insert(0, "packages/data-layer/src")


def _resolve_zai_api_key() -> str:
    """Resolve Z.AI API key from environment variable."""
    return os.getenv("Z_AI_TOKEN", "") or os.getenv("Z_AI_API_KEY", "").strip()


def _resolve_zai_base_url() -> str:
    """Resolve Z.AI base URL from environment variable."""
    return os.getenv("Z_AI_BASE_URL", "https://api.z.ai/api/coding/paas/v4").strip()


def _resolve_zai_model() -> str:
    """Resolve Z.AI model from environment variable."""
    return os.getenv("Z_AI_MODEL", "glm-5.1").strip()


def _provider() -> dict:
    """Return the Z.AI provider configuration (single legacy entry)."""
    base_url = _resolve_zai_base_url()

    return {
        "id": "zai-default",
        "name": "Z.AI (ZhipuAI)",
        "provider": "z_ai",
        "model": _resolve_zai_model(),
        "api_key": _resolve_zai_api_key(),
        "base_url": base_url,
        "model_params": {
            "temperature": 0.7,
            "max_tokens": 8192,
        },
        "role": "standard",
        "is_default": False,
    }


def _providers() -> list[dict]:
    """Return Z.AI provider configurations (light / standard / heavy)."""
    api_key = _resolve_zai_api_key()
    base_url = _resolve_zai_base_url()

    return [
        {
            "id": "zai-light",
            "name": "Z.AI glm-z1-flash (Light)",
            "provider": "z_ai",
            "model": "glm-z1-flash",
            "api_key": api_key,
            "base_url": base_url,
            "model_params": {"temperature": 0.6, "max_tokens": 2048},
            "role": "light",
            "is_default": False,
        },
        {
            "id": "zai-standard",
            "name": "Z.AI glm-4-flash (Standard)",
            "provider": "z_ai",
            "model": "glm-4-flash",
            "api_key": api_key,
            "base_url": base_url,
            "model_params": {"temperature": 0.7, "max_tokens": 4096},
            "role": "standard",
            "is_default": False,
        },
        {
            "id": "zai-heavy",
            "name": "Z.AI glm-4-plus (Heavy)",
            "provider": "z_ai",
            "model": "glm-4-plus",
            "api_key": api_key,
            "base_url": base_url,
            "model_params": {"temperature": 0.7, "max_tokens": 8192},
            "role": "heavy",
            "is_default": False,
        },
    ]


async def _seed(dry_run: bool = False) -> None:
    """Seed the Z.AI providers into the database."""
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
            print(f"    model: {p['model']}")
        print(f"  base_url: {providers[0]['base_url']}")
    finally:
        await postgres.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print provider row without writing to the database",
    )
    args = parser.parse_args()

    # Load .env and .env.tokens if present
    for filename in (".env", ".env.tokens"):
        env_file = os.path.join(os.path.dirname(__file__), "..", filename)
        if os.path.exists(env_file):
            with open(env_file) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, _, val = line.partition("=")
                        os.environ.setdefault(key.strip(), val.strip())

    # Check if API key is set
    if not _resolve_zai_api_key() and not args.dry_run:
        print("WARNING: Z_AI_API_KEY environment variable is not set.")
        print(
            "The provider will be created but will not be functional without an API key."
        )
        print("Set it in your .env file or run: export Z_AI_API_KEY=your-key-here")
        response = input("Continue anyway? (y/N): ").strip().lower()
        if response != "y":
            print("Aborted.")
            sys.exit(1)

    asyncio.run(_seed(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
