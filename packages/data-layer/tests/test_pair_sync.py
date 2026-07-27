"""Hermetic tests for the pair-sync derivation layer.

2026-07-22 centralization: ``model_pairs`` rows are now a derived
projection of ``llm_providers.is_default``. This file locks in:

- ``derive_active_pair_from_defaults()`` reads the live default rows
  and produces a ModelPair with the expected (chat, embedding, hyde,
  rerank) fields.
- ``sync_active_pair_from_defaults()`` upserts the derived pair via
  ``model_pair_upsert`` and respects ``auto_sync=false`` as a lock.
- ``RetrievalConfig.resolve()`` invokes sync before validate, so a
  pair whose row has drifted from defaults gets re-derived on boot.

We mock PostgresClient so the tests stay hermetic.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from monitor_data.retrieval.config import RetrievalConfig
from monitor_data.retrieval.pair_sync import (
    derive_active_pair_from_defaults,
    sync_active_pair_from_defaults,
)
from monitor_data.retrieval.pairs import ModelPair

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _row(role: str, model: str, provider: str, is_default: bool = True) -> dict:
    return {
        "id": f"id-{role}-{model}",
        "name": f"{role}-{model}",
        "role": role,
        "model": model,
        "provider": provider,
        "status": "connected",
        "is_default": is_default,
        "api_key": "k",
        "base_url": "",
        "embedding_dimension": 768,
    }


def _make_pg(
    *,
    chat_row=None,
    embedding_row=None,
    light_row=None,
    existing_pair: dict | None = None,
    auto_sync: bool = True,
) -> MagicMock:
    """Stub PostgresClient with the methods pair_sync actually calls."""
    pg = MagicMock()

    async def _get(role: str):
        return {
            "standard": chat_row,
            "embedding": embedding_row,
            "light": light_row,
        }.get(role)

    pg.provider_get_by_role = AsyncMock(side_effect=_get)

    async def _list(role: str) -> list[dict]:
        r = {
            "standard": chat_row,
            "embedding": embedding_row,
            "light": light_row,
        }.get(role)
        return [r] if r else []

    pg.provider_list_by_role = _list
    pg.model_pair_get = AsyncMock(return_value=existing_pair)
    pg.model_pair_list_active = AsyncMock(return_value=[existing_pair] if existing_pair else [])
    pg.model_pair_upsert = AsyncMock()
    pg.connect = AsyncMock()
    pg.close = AsyncMock()
    return pg


# ---------------------------------------------------------------------------
# derive_active_pair_from_defaults
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_derive_reads_default_chat_embedding_hyde_rerank():
    pg = _make_pg(
        chat_row=_row("standard", "MiniMax-M3", "minimax"),
        embedding_row=_row("embedding", "ollama/nomic-embed-text", "ollama"),
        light_row=_row("light", "MiniMax-M3", "minimax"),
    )
    pair = await derive_active_pair_from_defaults(pg, name="auto")
    assert pair.name == "auto"
    assert pair.status == "active"
    assert pair.chat_model == "MiniMax-M3"
    assert pair.chat_provider == "minimax"
    assert pair.chat_role == "standard"
    assert pair.embedding_model == "ollama/nomic-embed-text"
    assert pair.embedding_provider == "ollama"
    assert pair.embedding_dimension == 768
    assert pair.hyde_model == "MiniMax-M3"
    assert pair.hyde_provider == "minimax"
    assert pair.hyde_role == "light"
    assert pair.rerank_model == "MiniMax-M3"
    assert pair.rerank_provider == "minimax"
    assert pair.rerank_role == "light"


@pytest.mark.asyncio
async def test_derive_missing_chat_default_raises():
    pg = _make_pg(chat_row=None, embedding_row=_row("embedding", "m", "p"), light_row=_row("light", "m", "p"))
    with pytest.raises(RuntimeError, match="role='standard'"):
        await derive_active_pair_from_defaults(pg)


@pytest.mark.asyncio
async def test_derive_missing_embedding_default_raises():
    pg = _make_pg(chat_row=_row("standard", "m", "p"), embedding_row=None, light_row=_row("light", "m", "p"))
    with pytest.raises(RuntimeError, match="role='embedding'"):
        await derive_active_pair_from_defaults(pg)


@pytest.mark.asyncio
async def test_derive_missing_light_default_raises():
    pg = _make_pg(
        chat_row=_row("standard", "m", "p"),
        embedding_row=_row("embedding", "m", "p"),
        light_row=None,
    )
    with pytest.raises(RuntimeError, match="role='light'"):
        await derive_active_pair_from_defaults(pg)


@pytest.mark.asyncio
async def test_derive_falls_back_to_default_embedding_dimension():
    """Defensive: if the embedding row has no dimension column, the
    derivation falls back to the module's 768-dim default rather than
    silently writing 0."""
    pg = _make_pg(
        chat_row=_row("standard", "m", "p"),
        embedding_row={**_row("embedding", "m", "p"), "embedding_dimension": None},
        light_row=_row("light", "m", "p"),
    )
    pair = await derive_active_pair_from_defaults(pg)
    assert pair.embedding_dimension == 768


# ---------------------------------------------------------------------------
# sync_active_pair_from_defaults
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sync_upserts_derived_pair():
    pg = _make_pg(
        chat_row=_row("standard", "MiniMax-M3", "minimax"),
        embedding_row=_row("embedding", "ollama/nomic-embed-text", "ollama"),
        light_row=_row("light", "MiniMax-M3", "minimax"),
    )
    pair = await sync_active_pair_from_defaults(pg, name="vtm5-flash-nomic")
    assert pair is not None
    pg.model_pair_upsert.assert_awaited_once()
    upsert_payload = pg.model_pair_upsert.await_args.args[0]
    assert upsert_payload["name"] == "vtm5-flash-nomic"
    assert upsert_payload["chat_model"] == "MiniMax-M3"
    assert upsert_payload["auto_sync"] is True


@pytest.mark.asyncio
async def test_sync_respects_auto_sync_false_lock():
    """If the existing pair has auto_sync=false, sync is a no-op."""
    existing = {
        "name": "locked",
        "status": "active",
        "chat_model": "old-model",
        "chat_provider": "old-provider",
        "chat_role": "standard",
        "embedding_model": "old-embed",
        "embedding_provider": "old-embed-provider",
        "embedding_dimension": 768,
        "hyde_model": "old-hyde",
        "hyde_provider": "old-hyde-provider",
        "hyde_role": "light",
        "rerank_model": "old-rerank",
        "rerank_provider": "old-rerank-provider",
        "rerank_role": "light",
        "auto_sync": False,
    }
    pg = _make_pg(
        chat_row=_row("standard", "MiniMax-M3", "minimax"),
        embedding_row=_row("embedding", "m", "p"),
        light_row=_row("light", "MiniMax-M3", "minimax"),
        existing_pair=existing,
    )
    pair = await sync_active_pair_from_defaults(pg, name="locked")
    assert pair is not None
    # Locked pair returned unchanged.
    assert pair.chat_model == "old-model"
    pg.model_pair_upsert.assert_not_awaited()


@pytest.mark.asyncio
async def test_sync_dry_run_skips_upsert():
    pg = _make_pg(
        chat_row=_row("standard", "MiniMax-M3", "minimax"),
        embedding_row=_row("embedding", "m", "p"),
        light_row=_row("light", "MiniMax-M3", "minimax"),
    )
    pair = await sync_active_pair_from_defaults(pg, name="x", dry_run=True)
    assert pair is not None
    pg.model_pair_upsert.assert_not_awaited()


# ---------------------------------------------------------------------------
# RetrievalConfig.resolve — auto-sync integration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retrieval_config_resolve_calls_sync_before_validate():
    """resolve() must call sync_active_pair_from_defaults so the
    active pair's row aligns with live defaults before validate. We
    observe by patching the sync function and asserting it was called."""
    from unittest.mock import patch

    pg = _make_pg(
        chat_row=_row("standard", "MiniMax-M3", "minimax"),
        embedding_row=_row("embedding", "ollama/nomic-embed-text", "ollama"),
        light_row=_row("light", "MiniMax-M3", "minimax"),
        existing_pair={
            "name": "auto",
            "status": "active",
            "chat_model": "MiniMax-M3",
            "chat_provider": "minimax",
            "chat_role": "standard",
            "embedding_model": "ollama/nomic-embed-text",
            "embedding_provider": "ollama",
            "embedding_dimension": 768,
            "hyde_model": "MiniMax-M3",
            "hyde_provider": "minimax",
            "hyde_role": "light",
            "rerank_model": "MiniMax-M3",
            "rerank_provider": "minimax",
            "rerank_role": "light",
            "auto_sync": True,
        },
    )

    with patch(
        "monitor_data.retrieval.config.sync_active_pair_from_defaults",
        new=AsyncMock(return_value=ModelPair.from_dict(pg.model_pair_list_active.return_value[0])),
    ) as sync_mock:
        cfg = await RetrievalConfig.resolve(pg=pg)
    sync_mock.assert_awaited_once()
    assert cfg.pair.chat_model == "MiniMax-M3"
    assert cfg.pair.embedding_model == "ollama/nomic-embed-text"
