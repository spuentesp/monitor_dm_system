#!/usr/bin/env python3
"""Register the active embedding-gatekeeper pair in ``model_pairs``.

WHY THIS EXISTS
---------------
``PairRegistry.validate_active_pair()`` (the boot gate — see
``docs/architecture/RETRIEVAL_SERVICE.md`` and
``packages/data-layer/src/monitor_data/retrieval/pairs.py``) refuses to
start the retrieval layer unless a ``model_pairs`` row with
``status='active'`` matches the live ``llm_providers`` rows for chat,
embedding, hyde, and rerank. Before this script existed, that row was
inserted by hand from an ad hoc scratch script during the 2026-07-20
gatekeeper rollout — meaning the fix was real in that one database but
not reproducible: a fresh environment, or this database after a reset,
would have no pair registered and the system would refuse to boot with
no committed way to fix it. This script is that fix, checked in.

The pinned values below are not a guess — they were derived by querying
what ``provider_get_by_role()`` (the same lookup ``Embedder``/``PairLLM``
use at runtime) actually resolves to for each role, live, on 2026-07-20:
  - chat/standard  -> MiniMax-M3 (minimax) — the ``is_default=True`` row,
    NOT the initially-assumed gemini-2.5-flash.
  - embedding      -> ollama/nomic-embed-text (ollama) — repointed by
    ``seed_ollama_embedding_provider.py``.
  - hyde/rerank/light -> qwen2.5:latest (ollama) — bare model name,
    matching the live row exactly; PairLLM adds the litellm routing
    prefix itself (see ``pair_llm._litellm_model_string``).

If your live ``llm_providers`` rows differ (e.g. you've since changed
the default chat provider), run this with ``--chat-model``/
``--chat-provider`` overrides, or edit the row directly and re-run
``validate_active_pair()`` to confirm it still matches.

USAGE
-----
    uv run python scripts/seed_model_pair.py
    uv run python scripts/seed_model_pair.py --chat-model gemini-2.5-flash --chat-provider google_ai_studio
"""
from __future__ import annotations

import argparse
import asyncio
import sys

sys.path.insert(0, "packages/data-layer/src")

_DEFAULT_NAME = "vtm5-flash-nomic"

# 2026-07-22 centralization: when --read-live-defaults is set, ALL the
# pin values below are replaced by provider_get_by_role() lookups
# against the live llm_providers.is_default rows. The hardcoded defaults
# stay for environments where the operator hasn't run a provider seed
# script yet (or wants to pin values explicitly without consulting live
# rows).


async def _seed(
    *,
    name: str,
    chat_model: str,
    chat_provider: str,
    chat_role: str,
    embedding_model: str,
    embedding_provider: str,
    embedding_dimension: int,
    hyde_model: str,
    hyde_provider: str,
    hyde_role: str,
    rerank_model: str,
    rerank_provider: str,
    rerank_role: str,
    notes: str,
) -> None:
    from monitor_data.db.postgres import PostgresClient
    from monitor_data.retrieval.errors import IncompatiblePairError
    from monitor_data.retrieval.pairs import ModelPair, PairRegistry

    pair = ModelPair(
        name=name,
        status="active",
        chat_model=chat_model,
        chat_provider=chat_provider,
        chat_role=chat_role,
        embedding_model=embedding_model,
        embedding_provider=embedding_provider,
        embedding_dimension=embedding_dimension,
        hyde_model=hyde_model,
        hyde_provider=hyde_provider,
        hyde_role=hyde_role,
        rerank_model=rerank_model,
        rerank_provider=rerank_provider,
        rerank_role=rerank_role,
        notes=notes,
    )

    pg = PostgresClient()
    try:
        await pg.model_pair_upsert(pair.to_dict())
        print(f"  upserted model_pairs row: {name!r}")

        reg = PairRegistry(pg=pg)
        try:
            validated = await reg.validate_active_pair()
        except IncompatiblePairError as exc:
            print(f"  ! registered, but validate_active_pair() FAILS:\n{exc}")
            raise SystemExit(1) from exc
        print(f"  validate_active_pair() OK — active pair: {validated.name}")

        try:
            from monitor_data.retrieval import reset_retrieval_service

            reset_retrieval_service()
            print("  reset retrieval-service singleton")
        except Exception as exc:  # noqa: BLE001
            print(f"  ! could not reset retrieval-service singleton ({exc})")
    finally:
        await pg.close()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--read-live-defaults",
        action="store_true",
        help=(
            "Replace every (chat/embedding/hyde/rerank) value below with "
            "provider_get_by_role() results from the live llm_providers "
            "rows. Use this instead of --chat-model/--hyde-model/etc. "
            "overrides when you want the pair to track current defaults."
        ),
    )
    ap.add_argument("--name", default=_DEFAULT_NAME)
    ap.add_argument("--chat-model", default="MiniMax-M3")
    ap.add_argument("--chat-provider", default="minimax")
    ap.add_argument("--chat-role", default="standard")
    ap.add_argument("--embedding-model", default="ollama/nomic-embed-text")
    ap.add_argument("--embedding-provider", default="ollama")
    ap.add_argument("--embedding-dimension", type=int, default=768)
    ap.add_argument("--hyde-model", default="qwen2.5:latest")
    ap.add_argument("--hyde-provider", default="ollama")
    ap.add_argument("--hyde-role", default="light")
    ap.add_argument("--rerank-model", default="qwen2.5:latest")
    ap.add_argument("--rerank-provider", default="ollama")
    ap.add_argument("--rerank-role", default="light")
    ap.add_argument(
        "--notes",
        default=(
            "Registered by scripts/seed_model_pair.py. Chat/hyde/rerank values "
            "are whatever provider_get_by_role() resolves live for their roles "
            "-- re-run this script (with overrides if needed) after changing "
            "any llm_providers default."
        ),
    )
    args = ap.parse_args()

    # 2026-07-22 centralization: --read-live-defaults replaces the
    # hardcoded values with provider_get_by_role() results. Run inside
    # the same asyncio loop as _seed() so we share the client's pool.
    async def _maybe_read_live_defaults() -> bool:
        if not args.read_live_defaults:
            return True
        from monitor_data.db.postgres import PostgresClient

        pg = PostgresClient()
        try:
            chat = await pg.provider_get_by_role(args.chat_role)
            embed = await pg.provider_get_by_role("embedding")
            light = await pg.provider_get_by_role(args.hyde_role)
            if chat is None or embed is None or light is None:
                print(
                    "  ! --read-live-defaults requires a default row for each "
                    "role (chat_role, embedding, hyde_role). At least one is "
                    "missing. Run scripts/seed_*_provider.py first.",
                    file=sys.stderr,
                )
                return False
            args.chat_model = chat["model"]
            args.chat_provider = chat["provider"]
            args.embedding_model = embed["model"]
            args.embedding_provider = embed["provider"]
            embed_dim = embed.get("embedding_dimension") or 0
            if embed_dim > 0:
                args.embedding_dimension = int(embed_dim)
            args.hyde_model = light["model"]
            args.hyde_provider = light["provider"]
            args.rerank_model = light["model"]
            args.rerank_provider = light["provider"]
            print(
                f"  [read-live-defaults] chat=({args.chat_model}, "
                f"{args.chat_provider}); embed=({args.embedding_model}, "
                f"{args.embedding_provider}, dim={args.embedding_dimension}); "
                f"hyde/rerank=({args.hyde_model}, {args.hyde_provider})"
            )
            return True
        finally:
            await pg.close()

    async def _run_all() -> None:
        ok = await _maybe_read_live_defaults()
        if not ok:
            raise SystemExit(2)
        await _seed(
            name=args.name,
            chat_model=args.chat_model,
            chat_provider=args.chat_provider,
            chat_role=args.chat_role,
            embedding_model=args.embedding_model,
            embedding_provider=args.embedding_provider,
            embedding_dimension=args.embedding_dimension,
            hyde_model=args.hyde_model,
            hyde_provider=args.hyde_provider,
            hyde_role=args.hyde_role,
            rerank_model=args.rerank_model,
            rerank_provider=args.rerank_provider,
            rerank_role=args.rerank_role,
            notes=args.notes,
        )

    asyncio.run(_run_all())
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
