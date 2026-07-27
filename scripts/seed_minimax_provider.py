"""
Seed the llm_providers table with MiniMax AI providers.

MiniMax uses the Anthropic SDK with a custom base URL (Anthropic-compatible endpoint).

Three providers are created (light / standard / heavy):
  - minimax-light (M2.7):     fast responses       — LIGHT role
  - minimax-std   (M2.7):     role-playing, NPCs    — STANDARD role
  - minimax-m27   (M2.7):     coding, complex tasks — HEAVY role

Credentials are read from environment variables or .env.tokens:
  MINIMAX_TOKEN     API key
  MINIMAX_BASE_URL  Base URL (default: https://api.minimax.io/anthropic)

Usage (from repo root, with .env/.env.tokens loaded):
    python scripts/seed_minimax_provider.py
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

sys.path.insert(0, "packages/data-layer/src")


def _load_env() -> None:
    """Load .env and .env.tokens files."""
    for filename in (".env", ".env.tokens"):
        env_file = os.path.join(os.path.dirname(__file__), "..", filename)
        if os.path.exists(env_file):
            with open(env_file) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, _, val = line.partition("=")
                        os.environ.setdefault(key.strip(), val.strip())


def _resolve(key: str, default: str = "") -> str:
    return os.getenv(key, default).strip()


def _providers() -> list[dict]:
    """Return MiniMax provider configurations."""
    api_key = _resolve("MINIMAX_TOKEN") or _resolve("MINIMAX_API_KEY") or _resolve("MINIMAX_KEY")
    base_url = _resolve("MINIMAX_BASE_URL", "https://api.minimax.io/anthropic")

    return [
        {
            "id": "minimax-light",
            "name": "MiniMax M2.7 (Light)",
            "provider": "minimax",
            "model": "MiniMax-M2.7",
            "api_key": api_key,
            "base_url": base_url,
            "model_params": {
                "temperature": 0.7,
                "max_tokens": 2048,
            },
            "role": "light",
            "is_default": False,
        },
        {
            "id": "minimax-std",
            "name": "MiniMax M2.7 (Standard)",
            "provider": "minimax",
            "model": "MiniMax-M2.7",
            "api_key": api_key,
            "base_url": base_url,
            "model_params": {
                "temperature": 1.0,
                "max_tokens": 4096,
                "top_p": 0.95,
            },
            "role": "standard",
            "is_default": False,
        },
        {
            "id": "minimax-m27",
            "name": "MiniMax M2.7 (Heavy)",
            "provider": "minimax",
            "model": "MiniMax-M2.7",
            "api_key": api_key,
            "base_url": base_url,
            "model_params": {
                "temperature": 0.7,
                "max_tokens": 8192,
            },
            "role": "heavy",
            "is_default": False,
        },
    ]


async def _seed(dry_run: bool = False, sync_pair: bool = False) -> None:
    """Seed the MiniMax providers into the database."""
    providers = _providers()

    if dry_run:
        print("DRY RUN — providers that would be upserted:")
        for p in providers:
            display = dict(p)
            if display.get("api_key"):
                display["api_key"] = display["api_key"][:12] + "…"
            print(json.dumps(display, indent=2))
        return

    api_key = _resolve("MINIMAX_TOKEN") or _resolve("MINIMAX_API_KEY") or _resolve("MINIMAX_KEY")
    if not api_key:
        print("ERROR: MINIMAX_TOKEN (or MINIMAX_API_KEY) not set in env.")
        sys.exit(1)

    from monitor_data.db.postgres import PostgresClient

    postgres = PostgresClient()
    try:
        await postgres.connect()
        for provider in providers:
            await postgres.provider_upsert(provider)
            print(f"  ✓ upserted: {provider['id']} [{provider['role']}]")
            print(f"    model: {provider['model']}")
            print(f"    base_url: {provider['base_url']}")

        # 2026-07-22 centralization: --sync-pair re-derives the active
        # model_pair from llm_providers.is_default so any default flip
        # performed by this seed propagates to model_pairs automatically.
        if sync_pair:
            from monitor_data.retrieval.pair_sync import sync_active_pair_from_defaults

            active_rows = await postgres.model_pair_list_active()
            name = active_rows[0].get("name") if active_rows else "auto"
            try:
                pair = await sync_active_pair_from_defaults(postgres, name=name or "auto")
                if pair is not None:
                    print(
                        f"  [sync-pair] updated pair={pair.name} "
                        f"chat=({pair.chat_model},{pair.chat_provider}) "
                        f"hyde/rerank=({pair.hyde_model},{pair.hyde_provider})"
                    )
            except Exception as exc:  # noqa: BLE001
                print(f"  ! --sync-pair failed: {exc}")
    finally:
        await postgres.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--sync-pair",
        action="store_true",
        help=(
            "After upserting providers, re-derive the active model_pair "
            "from llm_providers.is_default so the chat/hyde/rerank fields "
            "auto-align with the new defaults."
        ),
    )
    args = parser.parse_args()

    _load_env()
    asyncio.run(_seed(dry_run=args.dry_run, sync_pair=args.sync_pair))


if __name__ == "__main__":
    main()
