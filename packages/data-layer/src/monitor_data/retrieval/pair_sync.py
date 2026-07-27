"""Pair sync — derive ``model_pairs`` rows from ``llm_providers.is_default``.

2026-07-22 centralization: the active model_pair row is no longer a
hand-authored config. Its ``chat/hyde/rerank_{model, provider, role}``
fields are derived from the ``is_default=true`` rows in
``llm_providers``. This module is the projection logic; it is called
from ``scripts/sync_pair_from_defaults.py``, from the
``RetrievalConfig.resolve()`` auto-sync hook, and from any provider
seed script that wants to flag ``--sync-pair``.

One source of truth (``llm_providers.is_default``), zero drift. If an
operator flips a default at the DB level, the next sync (manual or
auto) re-derives the pair to match.
"""

from __future__ import annotations

from dataclasses import asdict

from monitor_data.db.postgres import PostgresClient

from .pairs import ModelPair

# Default role mapping for the four pair components. The pair row's
# own ``chat_role`` etc. fields are derived from this; the chat LLM
# uses STANDARD by default, and the HyDE / rerank siblings use LIGHT.
_DEFAULT_CHAT_ROLE = "standard"
_DEFAULT_LIGHT_ROLE = "light"


async def derive_active_pair_from_defaults(
    pg: PostgresClient,
    *,
    name: str = "auto",
    embedding_dimension_fallback: int = 768,
) -> ModelPair:
    """Build a :class:`ModelPair` from the live ``llm_providers``
    ``is_default=true`` rows. Idempotent — call it any time the defaults
    change and you get a fresh row to upsert.

    Raises ``RuntimeError`` if no chat/embedding/hyde/rerank default
    row is available — that means the operator hasn't seeded the
    providers yet and we shouldn't fabricate one.

    ``embedding_dimension_fallback`` is used only if the chosen
    embedding row is missing the column (defensive — every real seed
    path writes ``embedding_dimension``).
    """
    chat = await pg.provider_get_by_role(_DEFAULT_CHAT_ROLE)
    if chat is None:
        raise RuntimeError(
            f"no llm_providers row with role={_DEFAULT_CHAT_ROLE!r} "
            "and is_default=true — seed a STANDARD provider first "
            "(see scripts/seed_minimax_provider.py)."
        )
    embedding = await pg.provider_get_by_role("embedding")
    if embedding is None:
        raise RuntimeError(
            "no llm_providers row with role='embedding' and is_default=true "
            "— seed an embedding provider first "
            "(see scripts/seed_ollama_embedding_provider.py)."
        )
    hyde = await pg.provider_get_by_role(_DEFAULT_LIGHT_ROLE)
    if hyde is None:
        raise RuntimeError(
            f"no llm_providers row with role={_DEFAULT_LIGHT_ROLE!r} "
            "and is_default=true — seed a LIGHT provider first "
            "(see scripts/seed_minimax_provider.py)."
        )
    rerank = await pg.provider_get_by_role(_DEFAULT_LIGHT_ROLE)
    if rerank is None:
        raise RuntimeError(
            f"no llm_providers row with role={_DEFAULT_LIGHT_ROLE!r} and is_default=true — seed a LIGHT provider first."
        )

    embed_dim = int(embedding.get("embedding_dimension") or embedding_dimension_fallback)
    if embed_dim <= 0:
        embed_dim = embedding_dimension_fallback

    pair = ModelPair(
        name=name,
        status="active",
        chat_model=str(chat["model"]),
        chat_provider=str(chat["provider"]),
        chat_role=_DEFAULT_CHAT_ROLE,
        embedding_model=str(embedding["model"]),
        embedding_provider=str(embedding["provider"]),
        embedding_dimension=embed_dim,
        hyde_model=str(hyde["model"]),
        hyde_provider=str(hyde["provider"]),
        hyde_role=_DEFAULT_LIGHT_ROLE,
        rerank_model=str(rerank["model"]),
        rerank_provider=str(rerank["provider"]),
        rerank_role=_DEFAULT_LIGHT_ROLE,
        notes="auto-derived from llm_providers.is_default (2026-07-22 centralization)",
    )
    return pair


async def sync_active_pair_from_defaults(
    pg: PostgresClient,
    *,
    name: str = "auto",
    auto_sync: bool = True,
    dry_run: bool = False,
) -> ModelPair | None:
    """Derive a pair from current defaults and upsert it.

    Returns the resulting :class:`ModelPair` (existing or new). If the
    existing row for ``name`` has ``auto_sync=false``, the sync is
    skipped and the existing row is returned unchanged. ``dry_run``
    builds the pair but skips the DB write.
    """
    existing = await pg.model_pair_get(name)
    if existing is not None and not bool(existing.get("auto_sync", True)):
        # Operator locked this pair — don't touch it.
        return ModelPair.from_dict(existing)

    new_pair = await derive_active_pair_from_defaults(pg, name=name)
    if dry_run:
        return new_pair

    payload = asdict(new_pair)
    payload["auto_sync"] = auto_sync
    await pg.model_pair_upsert(payload)
    return new_pair


__all__ = [
    "derive_active_pair_from_defaults",
    "sync_active_pair_from_defaults",
]
