"""Hermetic tests for the embedding gatekeeper.

Phase 1 (this file):
- ModelPair validation + serialisation.
- PairRegistry (active_pair, by_name, validate_active_pair,
  is_active_chat/embedding).
- Per-component match check via _provider_matches_live.

Phase 2 (added 2026-07-20):
- Embedder (sole litellm.aembedding site) — happy path, provider
  error, empty vector, live row missing, model/provider mismatch.
- PairLLM (sole litellm.acompletion site) — chat / hyde / rerank
  dispatch, provider error, empty response.

Future phases (planned): the compile-time AST scan for
"only one litellm.aembedding" / "no `db.embeddings` imports" tests.
"""

from __future__ import annotations

import re as _re
from pathlib import Path as _Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from monitor_data.retrieval.config import RetrievalConfig
from monitor_data.retrieval.contracts import Document, Hit
from monitor_data.retrieval.embedder import Embedder
from monitor_data.retrieval.errors import (
    EmbedderProviderError,
    IncompatiblePairError,
    PairLLMProviderError,
)
from monitor_data.retrieval.pair_llm import PairLLM
from monitor_data.retrieval.pairs import (
    ModelPair,
    PairRegistry,
    _provider_matches_live,
)

# ---------------------------------------------------------------------------
# Errors exist + are RuntimeError subclasses
# ---------------------------------------------------------------------------


def test_errors_are_runtimeerror_subclasses():
    for cls in (IncompatiblePairError, EmbedderProviderError, PairLLMProviderError):
        assert issubclass(cls, RuntimeError)
        # Each has a useful message.
        assert str(cls("msg")) == "msg"


# ---------------------------------------------------------------------------
# ModelPair validation
# ---------------------------------------------------------------------------


def test_model_pair_minimal_valid():
    p = ModelPair(
        name="vtm5-flash-nomic",
        chat_model="gemini-2.5-flash",
        chat_provider="google_ai_studio",
        embedding_model="ollama/nomic-embed-text",
        embedding_provider="ollama",
        embedding_dimension=768,
        hyde_model="ollama/qwen2.5:latest",
        hyde_provider="ollama",
        rerank_model="ollama/qwen2.5:latest",
        rerank_provider="ollama",
    )
    assert p.name == "vtm5-flash-nomic"
    assert p.status == "active"  # default
    assert p.embedding_dimension == 768


def test_model_pair_rejects_zero_dim():
    with pytest.raises(ValueError, match="embedding_dimension"):
        ModelPair(
            name="x",
            chat_model="c",
            chat_provider="p",
            embedding_model="e",
            embedding_provider="q",
            embedding_dimension=0,
            hyde_model="h",
            hyde_provider="p",
            rerank_model="r",
            rerank_provider="p",
        )


def test_model_pair_rejects_unknown_status():
    with pytest.raises(ValueError, match="status"):
        ModelPair(
            name="x",
            status="pending",
            chat_model="c",
            chat_provider="p",
            embedding_model="e",
            embedding_provider="q",
            embedding_dimension=768,
            hyde_model="h",
            hyde_provider="p",
            rerank_model="r",
            rerank_provider="p",
        )


def test_model_pair_rejects_unknown_role():
    with pytest.raises(ValueError, match="hyde_role"):
        ModelPair(
            name="x",
            chat_model="c",
            chat_provider="p",
            chat_role="standard",
            embedding_model="e",
            embedding_provider="q",
            embedding_dimension=768,
            hyde_model="h",
            hyde_provider="p",
            hyde_role="giga",
            rerank_model="r",
            rerank_provider="p",
            rerank_role="light",
        )


def test_model_pair_rejects_empty_field():
    with pytest.raises(ValueError, match="embedding_model"):
        ModelPair(
            name="x",
            chat_model="c",
            chat_provider="p",
            embedding_model="",
            embedding_provider="q",
            embedding_dimension=768,
            hyde_model="h",
            hyde_provider="p",
            rerank_model="r",
            rerank_provider="p",
        )


def test_model_pair_to_from_dict_roundtrip():
    p = ModelPair(
        name="x",
        chat_model="c",
        chat_provider="p",
        chat_role="heavy",
        embedding_model="e",
        embedding_provider="q",
        embedding_dimension=768,
        hyde_model="h",
        hyde_provider="p",
        hyde_role="light",
        rerank_model="r",
        rerank_provider="p",
        rerank_role="light",
    )
    d = p.to_dict()
    p2 = ModelPair.from_dict(d)
    assert p == p2


def test_model_pair_is_frozen():
    p = ModelPair(
        name="x",
        chat_model="c",
        chat_provider="p",
        embedding_model="e",
        embedding_provider="q",
        embedding_dimension=768,
        hyde_model="h",
        hyde_provider="p",
        rerank_model="r",
        rerank_provider="p",
    )
    with pytest.raises(Exception):  # FrozenInstanceError  # noqa: B017
        p.name = "y"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# _provider_matches_live — per-component
# ---------------------------------------------------------------------------


def test_provider_matches_live_chat():
    p = ModelPair(
        name="x",
        chat_model="gemini-2.5-flash",
        chat_provider="google_ai_studio",
        embedding_model="ollama/nomic-embed-text",
        embedding_provider="ollama",
        embedding_dimension=768,
        hyde_model="h",
        hyde_provider="p",
        rerank_model="r",
        rerank_provider="p",
    )
    assert _provider_matches_live(p, role="chat", model="gemini-2.5-flash", provider="google_ai_studio")
    assert not _provider_matches_live(p, role="chat", model="gemini-2.5-flash", provider="openai")
    assert not _provider_matches_live(p, role="chat", model="claude", provider="google_ai_studio")


def test_provider_matches_live_embedding_dimension_via_pair():
    """The dimension lives in the pair, not on the live row (the
    provider doesn't store it). The check is on (model, provider)
    only — the registry's validate_active_pair separately asserts
    the dim matches Qdrant."""
    p = ModelPair(
        name="x",
        chat_model="c",
        chat_provider="p",
        embedding_model="ollama/nomic-embed-text",
        embedding_provider="ollama",
        embedding_dimension=768,
        hyde_model="h",
        hyde_provider="p",
        rerank_model="r",
        rerank_provider="p",
    )
    assert _provider_matches_live(
        p,
        role="embedding",
        model="ollama/nomic-embed-text",
        provider="ollama",
    )
    assert not _provider_matches_live(
        p,
        role="embedding",
        model="gemini/gemini-embedding-001",
        provider="google_ai_studio",
    )


# ---------------------------------------------------------------------------
# PairRegistry.validate_active_pair — the boot gate
# ---------------------------------------------------------------------------


def _connected(role: str, model: str, provider: str) -> dict:
    """One llm_providers row in connected state."""
    return {
        "id": f"id-{role}",
        "name": role,
        "role": role,
        "model": model,
        "provider": provider,
        "status": "connected",
        "api_key": "",
        "base_url": "",
    }


def _by_role(rows: dict) -> AsyncMock:
    """Stub ``provider_get_by_role`` — the same lookup Embedder/PairLLM
    use — from a ``{role: row}`` mapping. Missing roles resolve None,
    matching the real query's behaviour when no row matches."""

    async def _get(role: str):
        return rows.get(role)

    return AsyncMock(side_effect=_get)


def _by_role_list(rows: dict) -> AsyncMock:
    """Stub ``provider_list_by_role`` — used by ``validate_active_pair``
    since 2026-07-22 centralization. Returns a list of one row per role
    (or empty list for missing roles), ordered is_default DESC."""

    async def _list(role: str):
        row = rows.get(role)
        return [row] if row else []

    return AsyncMock(side_effect=_list)


@pytest.mark.asyncio
async def test_validate_active_pair_happy_path():
    pair = ModelPair(
        name="vtm5-flash-nomic",
        chat_model="gemini-2.5-flash",
        chat_provider="google_ai_studio",
        chat_role="standard",
        embedding_model="ollama/nomic-embed-text",
        embedding_provider="ollama",
        embedding_dimension=768,
        hyde_model="ollama/qwen2.5:latest",
        hyde_provider="ollama",
        hyde_role="light",
        rerank_model="ollama/qwen2.5:latest",
        rerank_provider="ollama",
        rerank_role="light",
    )
    pg = MagicMock()
    pg.model_pair_list_active = AsyncMock(return_value=[pair.to_dict()])
    role_rows = {
        "standard": _connected("standard", "gemini-2.5-flash", "google_ai_studio"),
        "embedding": _connected("embedding", "ollama/nomic-embed-text", "ollama"),
        "light": _connected("light", "ollama/qwen2.5:latest", "ollama"),
    }
    pg.provider_get_by_role = _by_role(role_rows)
    pg.provider_list_by_role = _by_role_list(role_rows)
    pg.close = AsyncMock()
    reg = PairRegistry(pg=pg)
    out = await reg.validate_active_pair()
    assert out == pair


@pytest.mark.asyncio
async def test_validate_active_pair_no_pair_registered():
    pg = MagicMock()
    pg.model_pair_list_active = AsyncMock(return_value=[])
    pg.close = AsyncMock()
    reg = PairRegistry(pg=pg)
    with pytest.raises(IncompatiblePairError, match="no active model_pair"):
        await reg.validate_active_pair()


@pytest.mark.asyncio
async def test_validate_active_pair_chat_mismatch_fails_loud():
    pair = ModelPair(
        name="vtm5-flash-nomic",
        chat_model="gemini-2.5-flash",
        chat_provider="google_ai_studio",
        chat_role="standard",
        embedding_model="ollama/nomic-embed-text",
        embedding_provider="ollama",
        embedding_dimension=768,
        hyde_model="ollama/qwen2.5:latest",
        hyde_provider="ollama",
        hyde_role="light",
        rerank_model="ollama/qwen2.5:latest",
        rerank_provider="ollama",
        rerank_role="light",
    )
    pg = MagicMock()
    pg.model_pair_list_active = AsyncMock(return_value=[pair.to_dict()])
    # Live: chat row points at a different model.
    role_rows = {
        "standard": _connected("standard", "gemini-2.5-flash-lite", "google_ai_studio"),
        "embedding": _connected("embedding", "ollama/nomic-embed-text", "ollama"),
        "light": _connected("light", "ollama/qwen2.5:latest", "ollama"),
    }
    pg.provider_get_by_role = _by_role(role_rows)
    pg.provider_list_by_role = _by_role_list(role_rows)
    pg.close = AsyncMock()
    reg = PairRegistry(pg=pg)
    with pytest.raises(IncompatiblePairError, match="chat: pair wants"):
        await reg.validate_active_pair()


@pytest.mark.asyncio
async def test_validate_active_pair_embedding_mismatch_fails_loud():
    pair = ModelPair(
        name="vtm5-flash-nomic",
        chat_model="gemini-2.5-flash",
        chat_provider="google_ai_studio",
        chat_role="standard",
        embedding_model="ollama/nomic-embed-text",
        embedding_provider="ollama",
        embedding_dimension=768,
        hyde_model="ollama/qwen2.5:latest",
        hyde_provider="ollama",
        hyde_role="light",
        rerank_model="ollama/qwen2.5:latest",
        rerank_provider="ollama",
        rerank_role="light",
    )
    pg = MagicMock()
    pg.model_pair_list_active = AsyncMock(return_value=[pair.to_dict()])
    # Live: embedding row points at gemini (the bug we caught).
    role_rows = {
        "standard": _connected("standard", "gemini-2.5-flash", "google_ai_studio"),
        "embedding": _connected("embedding", "gemini/gemini-embedding-001", "google_ai_studio"),
        "light": _connected("light", "ollama/qwen2.5:latest", "ollama"),
    }
    pg.provider_get_by_role = _by_role(role_rows)
    pg.provider_list_by_role = _by_role_list(role_rows)
    pg.close = AsyncMock()
    reg = PairRegistry(pg=pg)
    with pytest.raises(IncompatiblePairError, match="embedding: pair wants"):
        await reg.validate_active_pair()


@pytest.mark.asyncio
async def test_validate_active_pair_missing_role_row():
    """If no connected llm_providers row exists for the pair's role,
    the gatekeeper names the missing role."""
    pair = ModelPair(
        name="vtm5-flash-nomic",
        chat_model="gemini-2.5-flash",
        chat_provider="google_ai_studio",
        chat_role="standard",
        embedding_model="ollama/nomic-embed-text",
        embedding_provider="ollama",
        embedding_dimension=768,
        hyde_model="ollama/qwen2.5:latest",
        hyde_provider="ollama",
        hyde_role="light",
        rerank_model="ollama/qwen2.5:latest",
        rerank_provider="ollama",
        rerank_role="light",
    )
    pg = MagicMock()
    pg.model_pair_list_active = AsyncMock(return_value=[pair.to_dict()])
    # Live: no embedding row at all.
    role_rows = {
        "standard": _connected("standard", "gemini-2.5-flash", "google_ai_studio"),
        "light": _connected("light", "ollama/qwen2.5:latest", "ollama"),
    }
    pg.provider_get_by_role = _by_role(role_rows)
    pg.provider_list_by_role = _by_role_list(role_rows)
    pg.close = AsyncMock()
    reg = PairRegistry(pg=pg)
    with pytest.raises(IncompatiblePairError, match="embedding.*no llm_providers row"):
        await reg.validate_active_pair()


@pytest.mark.asyncio
async def test_validate_active_pair_accepts_non_default_row_for_role():
    """2026-07-22 centralization: validation passes if ANY row for the
    role matches the pair's expected (model, provider), not only the
    default. The default row is still surfaced in the error message
    when validation fails (so operators can see the runtime pick) but
    doesn't gate boot.

    Simulates a real failure mode: pair is pinned to a non-default
    local provider (ollama/qwen) while is_default=true points at
    MiniMax. Pre-centralization, this would have failed boot; now it
    passes because the operator's local row still exists for the role.
    """
    pair = ModelPair(
        name="vtm5-flash-nomic",
        chat_model="ollama/qwen2.5:latest",
        chat_provider="ollama",
        chat_role="light",
        embedding_model="ollama/nomic-embed-text",
        embedding_provider="ollama",
        embedding_dimension=768,
        hyde_model="ollama/qwen2.5:latest",
        hyde_provider="ollama",
        hyde_role="light",
        rerank_model="ollama/qwen2.5:latest",
        rerank_provider="ollama",
        rerank_role="light",
    )
    pg = MagicMock()
    pg.model_pair_list_active = AsyncMock(return_value=[pair.to_dict()])
    # Two light rows: the default is MiniMax, but a non-default ollama row
    # matches the pair's pinned (model, provider). Validation must pass.
    pg.provider_list_by_role = AsyncMock(
        side_effect=lambda role: {
            "light": [
                {**_connected("light", "MiniMax-M3", "minimax"), "is_default": True},
                _connected("light", "ollama/qwen2.5:latest", "ollama"),
            ],
            "embedding": [_connected("embedding", "ollama/nomic-embed-text", "ollama")],
        }.get(role, [])
    )
    pg.close = AsyncMock()
    reg = PairRegistry(pg=pg)
    out = await reg.validate_active_pair()
    assert out.chat_model == "ollama/qwen2.5:latest"
    assert out.chat_provider == "ollama"


@pytest.mark.asyncio
async def test_validate_active_pair_default_only_match_still_fails_when_no_other_row():
    """The inverse of the above: if NO row for the role matches the pair,
    the gatekeeper still fails — the looser check doesn't override the
    safety guarantee that some row must point at what the pair pins."""
    pair = ModelPair(
        name="vtm5-flash-nomic",
        chat_model="gemini-2.5-flash",
        chat_provider="google_ai_studio",
        chat_role="standard",
        embedding_model="ollama/nomic-embed-text",
        embedding_provider="ollama",
        embedding_dimension=768,
        hyde_model="ollama/qwen2.5:latest",
        hyde_provider="ollama",
        hyde_role="light",
        rerank_model="ollama/qwen2.5:latest",
        rerank_provider="ollama",
        rerank_role="light",
    )
    pg = MagicMock()
    pg.model_pair_list_active = AsyncMock(return_value=[pair.to_dict()])
    pg.provider_list_by_role = AsyncMock(
        side_effect=lambda role: {
            "standard": [
                {**_connected("standard", "MiniMax-M3", "minimax"), "is_default": True},
                _connected("standard", "claude-3.5", "anthropic"),
            ],
            "embedding": [_connected("embedding", "ollama/nomic-embed-text", "ollama")],
            "light": [_connected("light", "ollama/qwen2.5:latest", "ollama")],
        }.get(role, [])
    )
    pg.close = AsyncMock()
    reg = PairRegistry(pg=pg)
    with pytest.raises(IncompatiblePairError, match="chat: pair wants"):
        await reg.validate_active_pair()


@pytest.mark.asyncio
async def test_validate_active_pair_multiple_active_rows_errors():
    """Two active rows would be ambiguous — the unique partial index
    prevents this, but if a manual SQL edit bypasses it, the gatekeeper
    names the problem."""
    pair = ModelPair(
        name="a",
        chat_model="c",
        chat_provider="p",
        embedding_model="e",
        embedding_provider="q",
        embedding_dimension=768,
        hyde_model="h",
        hyde_provider="p",
        rerank_model="r",
        rerank_provider="p",
    )
    pg = MagicMock()
    pg.model_pair_list_active = AsyncMock(return_value=[pair.to_dict(), pair.to_dict()])
    pg.close = AsyncMock()
    reg = PairRegistry(pg=pg)
    with pytest.raises(IncompatiblePairError, match="2 active rows"):
        await reg.validate_active_pair()


@pytest.mark.asyncio
async def test_active_pair_returns_none_when_no_row():
    pg = MagicMock()
    pg.model_pair_list_active = AsyncMock(return_value=[])
    pg.close = AsyncMock()
    reg = PairRegistry(pg=pg)
    assert await reg.active_pair() is None


@pytest.mark.asyncio
async def test_active_pair_returns_dataclass():
    pair = ModelPair(
        name="x",
        chat_model="c",
        chat_provider="p",
        embedding_model="e",
        embedding_provider="q",
        embedding_dimension=768,
        hyde_model="h",
        hyde_provider="p",
        rerank_model="r",
        rerank_provider="p",
    )
    pg = MagicMock()
    pg.model_pair_list_active = AsyncMock(return_value=[pair.to_dict()])
    pg.close = AsyncMock()
    reg = PairRegistry(pg=pg)
    out = await reg.active_pair()
    assert isinstance(out, ModelPair)
    assert out.name == "x"


@pytest.mark.asyncio
async def test_is_active_chat_and_embedding():
    pair = ModelPair(
        name="x",
        chat_model="gemini-2.5-flash",
        chat_provider="p",
        embedding_model="ollama/nomic-embed-text",
        embedding_provider="q",
        embedding_dimension=768,
        hyde_model="h",
        hyde_provider="p",
        rerank_model="r",
        rerank_provider="p",
    )
    pg = MagicMock()
    pg.model_pair_list_active = AsyncMock(return_value=[pair.to_dict()])
    pg.close = AsyncMock()
    reg = PairRegistry(pg=pg)
    assert await reg.is_active_chat("gemini-2.5-flash") is True
    assert await reg.is_active_chat("claude") is False
    assert await reg.is_active_embedding("ollama/nomic-embed-text") is True
    assert await reg.is_active_embedding("gemini/gemini-embedding-001") is False


# ===========================================================================
# Phase 2 — Embedder (sole litellm.aembedding site)
# ===========================================================================


def _embed_row(model: str, provider: str, api_key: str = "k", base_url: str = "") -> dict:
    return {
        "id": "embed-id",
        "name": "embedding",
        "role": "embedding",
        "model": model,
        "provider": provider,
        "status": "connected",
        "api_key": api_key,
        "base_url": base_url,
    }


def _sample_pair() -> ModelPair:
    return ModelPair(
        name="vtm5-flash-nomic",
        chat_model="gemini-2.5-flash",
        chat_provider="google_ai_studio",
        chat_role="standard",
        embedding_model="ollama/nomic-embed-text",
        embedding_provider="ollama",
        embedding_dimension=768,
        hyde_model="ollama/qwen2.5:latest",
        hyde_provider="ollama",
        hyde_role="light",
        rerank_model="ollama/qwen2.5:latest",
        rerank_provider="ollama",
        rerank_role="light",
    )


@pytest.mark.asyncio
async def test_embedder_happy_path_calls_litellm_with_pinned_args():
    pair = _sample_pair()
    pg = MagicMock()
    pg.provider_get_by_role = AsyncMock(return_value=_embed_row("ollama/nomic-embed-text", "ollama"))
    pg.close = AsyncMock()
    e = Embedder(pair, pg=pg, preflight_enabled=False)

    captured: dict = {}

    async def _fake_aembedding(**kwargs):
        captured.update(kwargs)
        return MagicMock(data=[{"embedding": [0.1, 0.2, 0.3]}])

    with patch("monitor_data.retrieval.embedder.litellm.aembedding", new=_fake_aembedding):
        vec = await e.embed("hello")
    assert vec == [0.1, 0.2, 0.3]
    # The exact kwargs we built — model + input + api_key (no base_url).
    assert captured["model"] == "ollama/nomic-embed-text"
    assert captured["input"] == ["hello"]
    assert captured["api_key"] == "k"
    assert "api_base" not in captured


@pytest.mark.asyncio
async def test_embedder_passes_base_url_when_set():
    pair = _sample_pair()
    pg = MagicMock()
    pg.provider_get_by_role = AsyncMock(
        return_value=_embed_row("ollama/nomic-embed-text", "ollama", base_url="http://x:11434")
    )
    pg.close = AsyncMock()
    e = Embedder(pair, pg=pg, preflight_enabled=False)

    captured: dict = {}

    async def _fake_aembedding(**kwargs):
        captured.update(kwargs)
        return MagicMock(data=[{"embedding": [0.1]}])

    with patch("monitor_data.retrieval.embedder.litellm.aembedding", new=_fake_aembedding):
        await e.embed("hi")
    assert captured.get("api_base") == "http://x:11434"


@pytest.mark.asyncio
async def test_embedder_batch():
    pair = _sample_pair()
    pg = MagicMock()
    pg.provider_get_by_role = AsyncMock(return_value=_embed_row("ollama/nomic-embed-text", "ollama"))
    pg.close = AsyncMock()
    e = Embedder(pair, pg=pg, preflight_enabled=False)

    async def _fake_aembedding(**kwargs):
        assert kwargs["input"] == ["a", "b", "c"]
        return MagicMock(
            data=[
                {"embedding": [0.1, 0.1]},
                {"embedding": [0.2, 0.2]},
                {"embedding": [0.3, 0.3]},
            ]
        )

    with patch("monitor_data.retrieval.embedder.litellm.aembedding", new=_fake_aembedding):
        out = await e.embed_batch(["a", "b", "c"])
    assert out == [[0.1, 0.1], [0.2, 0.2], [0.3, 0.3]]


@pytest.mark.asyncio
async def test_embedder_empty_batch_is_no_op():
    pair = _sample_pair()
    pg = MagicMock()
    e = Embedder(pair, pg=pg, preflight_enabled=False)
    assert await e.embed_batch([]) == []


@pytest.mark.asyncio
async def test_embedder_provider_error_raises_typed():
    pair = _sample_pair()
    pg = MagicMock()
    pg.provider_get_by_role = AsyncMock(return_value=_embed_row("ollama/nomic-embed-text", "ollama"))
    pg.close = AsyncMock()
    e = Embedder(pair, pg=pg, preflight_enabled=False)

    async def _boom(**_):
        raise RuntimeError("provider down")

    with patch("monitor_data.retrieval.embedder.litellm.aembedding", new=_boom):
        with pytest.raises(EmbedderProviderError, match="provider down"):
            await e.embed("hi")


@pytest.mark.asyncio
async def test_embedder_empty_vector_raises():
    pair = _sample_pair()
    pg = MagicMock()
    pg.provider_get_by_role = AsyncMock(return_value=_embed_row("ollama/nomic-embed-text", "ollama"))
    pg.close = AsyncMock()
    e = Embedder(pair, pg=pg, preflight_enabled=False)

    async def _empty(**_):
        return MagicMock(data=[{"embedding": []}])

    with patch("monitor_data.retrieval.embedder.litellm.aembedding", new=_empty):
        with pytest.raises(EmbedderProviderError, match="empty vector"):
            await e.embed("hi")


@pytest.mark.asyncio
async def test_embedder_missing_live_row_raises():
    pair = _sample_pair()
    pg = MagicMock()
    pg.provider_get_by_role = AsyncMock(return_value=None)
    pg.close = AsyncMock()
    e = Embedder(pair, pg=pg, preflight_enabled=False)
    with pytest.raises(EmbedderProviderError, match="no llm_providers row"):
        await e.embed("hi")


@pytest.mark.asyncio
async def test_embedder_live_model_drift_fails_loud():
    pair = _sample_pair()
    pg = MagicMock()
    # Live row's model differs from the pair (this is the bug the gatekeeper
    # is designed to prevent).
    pg.provider_get_by_role = AsyncMock(return_value=_embed_row("gemini/gemini-embedding-001", "google_ai_studio"))
    pg.close = AsyncMock()
    e = Embedder(pair, pg=pg, preflight_enabled=False)
    with pytest.raises(EmbedderProviderError, match="does not match active pair.embedding_model"):
        await e.embed("hi")


# ===========================================================================
# Phase 2 — PairLLM (sole litellm.acompletion site)
# ===========================================================================


def _chat_row(model: str, provider: str, api_key: str = "ck", base_url: str = "") -> dict:
    return {
        "id": "chat-id",
        "name": "standard",
        "role": "standard",
        "model": model,
        "provider": provider,
        "status": "connected",
        "api_key": api_key,
        "base_url": base_url,
    }


def _light_row(model: str, provider: str) -> dict:
    return {
        "id": "light-id",
        "name": "light",
        "role": "light",
        "model": model,
        "provider": provider,
        "status": "connected",
        "api_key": "lk",
        "base_url": "",
    }


@pytest.mark.asyncio
async def test_pair_llm_dispatches_chat_component():
    pair = _sample_pair()
    pg = MagicMock()
    pg.provider_get_by_role = AsyncMock(return_value=_chat_row("gemini-2.5-flash", "google_ai_studio"))
    pg.close = AsyncMock()
    llm = PairLLM(pair, pg=pg)

    captured: dict = {}

    async def _fake_acompletion(**kwargs):
        captured.update(kwargs)
        return MagicMock(choices=[MagicMock(message=MagicMock(content="hello there"))])

    with patch("monitor_data.retrieval.pair_llm.litellm.acompletion", new=_fake_acompletion):
        out = await llm.acompletion("chat", "hi")
    assert out == "hello there"
    # Bare model name + non-anthropic/minimax provider -> litellm needs an
    # explicit "openai/" prefix to route an OpenAI-compatible call; see
    # _litellm_model_string.
    assert captured["model"] == "openai/gemini-2.5-flash"
    assert captured["api_key"] == "ck"
    assert captured["messages"][0]["content"] == "hi"


@pytest.mark.asyncio
async def test_pair_llm_dispatches_hyde_with_pair_role():
    pair = _sample_pair()
    pg = MagicMock()
    pg.provider_get_by_role = AsyncMock(return_value=_light_row("ollama/qwen2.5:latest", "ollama"))
    pg.close = AsyncMock()
    llm = PairLLM(pair, pg=pg)
    captured: dict = {}

    async def _fake_acompletion(**kwargs):
        captured.update(kwargs)
        return MagicMock(choices=[MagicMock(message=MagicMock(content="hyde doc"))])

    with patch("monitor_data.retrieval.pair_llm.litellm.acompletion", new=_fake_acompletion):
        out = await llm.acompletion("hyde", "rewrite me", max_tokens=200, temperature=0.7)
    assert out == "hyde doc"
    assert captured["model"] == "ollama/qwen2.5:latest"
    assert captured["max_tokens"] == 200
    assert captured["temperature"] == 0.7


@pytest.mark.asyncio
async def test_pair_llm_dispatches_rerank():
    pair = _sample_pair()
    pg = MagicMock()
    pg.provider_get_by_role = AsyncMock(return_value=_light_row("ollama/qwen2.5:latest", "ollama"))
    pg.close = AsyncMock()
    llm = PairLLM(pair, pg=pg)
    captured: dict = {}

    async def _fake_acompletion(**kwargs):
        captured.update(kwargs)
        return MagicMock(choices=[MagicMock(message=MagicMock(content="5,7,3"))])

    with patch("monitor_data.retrieval.pair_llm.litellm.acompletion", new=_fake_acompletion):
        out = await llm.acompletion("rerank", "rank these")
    assert out == "5,7,3"
    assert captured["model"] == "ollama/qwen2.5:latest"


@pytest.mark.asyncio
async def test_pair_llm_bare_model_gets_openai_prefix_and_placeholder_key():
    """Regression: a live llm_providers row for an OpenAI-compatible local
    endpoint (e.g. ollama-local) stores the bare model name with no api_key.
    litellm can't route a bare model string or call without *some* api_key —
    caught live 2026-07-20 (BadRequestError: LLM Provider NOT provided).
    """
    pair = ModelPair(
        name="vtm5-flash-nomic",
        chat_model="gemini-2.5-flash",
        chat_provider="google_ai_studio",
        chat_role="standard",
        embedding_model="ollama/nomic-embed-text",
        embedding_provider="ollama",
        embedding_dimension=768,
        hyde_model="qwen2.5:latest",
        hyde_provider="ollama",
        hyde_role="light",
        rerank_model="qwen2.5:latest",
        rerank_provider="ollama",
        rerank_role="light",
    )
    pg = MagicMock()
    pg.provider_get_by_role = AsyncMock(
        return_value={
            "id": "light-id",
            "name": "light",
            "role": "light",
            "model": "qwen2.5:latest",
            "provider": "ollama",
            "status": "connected",
            "api_key": "",
            "base_url": "http://localhost:11434/v1",
        }
    )
    pg.close = AsyncMock()
    llm = PairLLM(pair, pg=pg)
    captured: dict = {}

    async def _fake_acompletion(**kwargs):
        captured.update(kwargs)
        return MagicMock(choices=[MagicMock(message=MagicMock(content="hyde doc"))])

    with patch("monitor_data.retrieval.pair_llm.litellm.acompletion", new=_fake_acompletion):
        await llm.acompletion("hyde", "rewrite me")
    assert captured["model"] == "openai/qwen2.5:latest"
    assert captured["api_key"] == "not-needed"
    assert captured["api_base"] == "http://localhost:11434/v1"


@pytest.mark.asyncio
async def test_pair_llm_provider_error_raises_typed():
    pair = _sample_pair()
    pg = MagicMock()
    pg.provider_get_by_role = AsyncMock(return_value=_chat_row("gemini-2.5-flash", "google_ai_studio"))
    pg.close = AsyncMock()
    llm = PairLLM(pair, pg=pg)

    async def _boom(**_):
        raise RuntimeError("rate limited")

    with patch("monitor_data.retrieval.pair_llm.litellm.acompletion", new=_boom):
        with pytest.raises(PairLLMProviderError, match="rate limited"):
            await llm.acompletion("chat", "hi")


@pytest.mark.asyncio
async def test_pair_llm_empty_response_raises():
    pair = _sample_pair()
    pg = MagicMock()
    pg.provider_get_by_role = AsyncMock(return_value=_chat_row("gemini-2.5-flash", "google_ai_studio"))
    pg.close = AsyncMock()
    llm = PairLLM(pair, pg=pg)

    async def _empty(**_):
        return MagicMock(choices=[])

    with patch("monitor_data.retrieval.pair_llm.litellm.acompletion", new=_empty):
        with pytest.raises(PairLLMProviderError, match="empty response"):
            await llm.acompletion("chat", "hi")


@pytest.mark.asyncio
async def test_pair_llm_missing_live_row_raises():
    pair = _sample_pair()
    pg = MagicMock()
    pg.provider_get_by_role = AsyncMock(return_value=None)
    pg.close = AsyncMock()
    llm = PairLLM(pair, pg=pg)
    with pytest.raises(PairLLMProviderError, match="no llm_providers row"):
        await llm.acompletion("chat", "hi")


@pytest.mark.asyncio
async def test_pair_llm_unknown_component_raises():
    pair = _sample_pair()
    pg = MagicMock()
    pg.close = AsyncMock()
    llm = PairLLM(pair, pg=pg)
    with pytest.raises(PairLLMProviderError, match="unknown PairLLM component"):
        await llm.acompletion("nonsense", "hi")


@pytest.mark.asyncio
async def test_pair_llm_live_model_drift_fails_loud():
    """This is the partner to the Embedder's same test — changing the
    llm_providers row without the pair is a contract violation."""
    pair = _sample_pair()
    pg = MagicMock()
    pg.provider_get_by_role = AsyncMock(return_value=_chat_row("claude-3.5", "anthropic"))
    pg.close = AsyncMock()
    llm = PairLLM(pair, pg=pg)
    with pytest.raises(PairLLMProviderError, match="does not match active pair.chat_model"):
        await llm.acompletion("chat", "hi")


# ===========================================================================
# Phase 4 — Compile-time AST scan tests
# ===========================================================================
# The whole point of the gatekeeper is to make "embed via anything other
# than the Embedder" impossible. These tests assert that at the file-
# scanning level: only embedder.py calls litellm.aembedding, only
# pair_llm.py calls litellm.acompletion (for retrieval), and nothing
# imports the deleted monitor_data.db.embeddings module. If any future
# PR sneaks a bypass back in, these tests fail and the regression is
# visible.
# ===========================================================================


_REPO_ROOT = _Path(__file__).resolve().parents[3]  # tests/test_*.py → packages → repo


def _iter_python_files(include_tests: bool = True):
    """Yield every .py file under the repo root, excluding .venv, __pycache__,
    the docs directory, and any sibling worktrees under .claude/worktrees/
    (those are checked-out copies of the repo for parallel work — not the
    working tree we're auditing).
    """
    for p in _REPO_ROOT.rglob("*.py"):
        s = str(p)
        if any(
            seg in s
            for seg in (
                ".venv",
                "__pycache__",
                "/docs/",
                "/.git/",
                "/.claude/worktrees/",
            )
        ):
            continue
        if not include_tests and "/tests/" in s:
            continue
        yield p


def _files_with_call(call_name: str, include_tests: bool = True) -> list[tuple[str, list[int]]]:
    """Find files that contain a *real* call to ``call_name`` (not just
    a docstring mention). We strip triple-quoted strings + line comments
    before checking so docstrings/comments don't false-positive.
    """
    hits: list[tuple[str, list[int]]] = []
    for p in _iter_python_files(include_tests=include_tests):
        text = p.read_text()
        # Drop triple-quoted strings (incl. docstrings).
        text = _re.sub(r'"""[\s\S]*?"""', "", text)
        text = _re.sub(r"'''[\s\S]*?'''", "", text)
        # Drop line comments.
        text = _re.sub(r"#[^\n]*", "", text)
        line_hits: list[int] = []
        for i, line in enumerate(text.splitlines(), start=1):
            if call_name in line:
                line_hits.append(i)
        if line_hits:
            hits.append((str(p.relative_to(_REPO_ROOT)), line_hits))
    return hits


def test_only_one_embedder_path_litellm_aembedding():
    """``litellm.aembedding`` may appear (as a real call) only inside
    ``retrieval/embedder.py`` and ``retrieval/embedding_health.py``
    (the pre-flight probe — fail-loud at the 0th embed rather than
    timing out at chunk 120). No other production module is allowed
    to call it.
    """
    hits = _files_with_call("litellm.aembedding", include_tests=False)
    allowed = (
        "retrieval/embedder.py",
        "retrieval/embedding_health.py",
    )
    bad = [h for h in hits if not h[0].endswith(allowed)]
    assert not bad, (
        f"litellm.aembedding called outside the embedder pair "
        f"({allowed}): {bad}. Embeddings must go through the single "
        "Embedder (gatekeeper). If you need a new embedder call, "
        "add it to embedder.py or embedding_health.py."
    )


def test_only_one_pair_llm_path_litellm_acompletion():
    """``litellm.acompletion`` in the retrieval layer may appear (as a
    real call) only inside ``retrieval/pair_llm.py``. No production
    module in the retrieval layer is allowed to call it directly.
    """
    hits = _files_with_call("litellm.acompletion", include_tests=False)
    # Restrict to retrieval layer.
    in_retrieval = [h for h in hits if "/retrieval/" in h[0]]
    bad = [h for h in in_retrieval if not h[0].endswith("retrieval/pair_llm.py")]
    assert not bad, (
        f"litellm.acompletion called outside retrieval/pair_llm.py "
        f"(in the retrieval layer): {bad}. Retrieval-side LLM calls "
        "must go through the single PairLLM."
    )


def test_no_module_imports_the_deleted_embeddings():
    """Nothing in the repo may import ``monitor_data.db.embeddings``.
    The module was deleted; any such import is a regression and must
    go through RetrievalService instead.
    """
    offenders: list[tuple[str, list[int]]] = []
    for p in _iter_python_files(include_tests=True):
        text = p.read_text()
        # Strip docstrings + line comments so the docstring mentions in
        # errors.py / pairs.py (which describe the deleted module) don't
        # false-positive.
        stripped = _re.sub(r'"""[\s\S]*?"""', "", text)
        stripped = _re.sub(r"'''[\s\S]*?'''", "", stripped)
        for i, line in enumerate(stripped.splitlines(), start=1):
            # Only flag actual import statements.
            if _re.search(r"^\s*(from|import)\s+monitor_data\.db\.embeddings", line):
                offenders.append((str(p.relative_to(_REPO_ROOT)), i))
    assert not offenders, (
        f"the deleted module monitor_data.db.embeddings is imported at: {offenders}. "
        "Embeddings go through monitor_data.retrieval.RetrievalService."
    )


def test_agent_call_sites_go_through_gatekeeper():
    """Audit: no module under packages/agents/ should reference
    ``monitor_data.db.embeddings`` or call ``litellm.aembedding``
    directly. Embedding access in agent code MUST go through
    ``monitor_data.retrieval.default_retrieval_service()``.
    """
    bad: list[tuple[str, str, int]] = []
    for p in _REPO_ROOT.glob("packages/agents/**/*.py"):
        text = p.read_text()
        for i, line in enumerate(text.splitlines(), start=1):
            stripped = line.lstrip()
            if stripped.startswith("#"):
                continue
            if "monitor_data.db.embeddings" in line:
                bad.append((str(p.relative_to(_REPO_ROOT)), "db.embeddings import", i))
            if "litellm.aembedding" in line and "embedder.py" not in str(p):
                # Any non-embedder call to litellm.aembedding in agents/.
                bad.append((str(p.relative_to(_REPO_ROOT)), "litellm.aembedding", i))
    assert not bad, f"agent call sites must go through RetrievalService, not bypass to the embedder: {bad}"


# ===========================================================================
# Phase 4 — Common-poisoning-pattern regression tests
# ===========================================================================
# The original bug (2026-07-20) was an embedding model A used to store
# a Qdrant collection, then model B used to query it — same dim, no
# way to tell from the dim alone. The gatekeeper prevents the *active*
# pair from drifting, but the *collection* can still be poisoned if an
# operator runs the reindex script wrong. These tests lock in the
# recovery paths so a future change to ensure_collection / index
# can't silently re-introduce the bug.
# ===========================================================================


@pytest.mark.asyncio
async def test_ensure_collection_warns_on_legacy_no_meta():
    """Legacy collection (no recorded meta) with same dim: warns, doesn't
    hard-fail. The next index() call records the active model."""
    from monitor_data.retrieval.pairs import ModelPair
    from monitor_data.retrieval.service import RetrievalService

    pair = ModelPair(
        name="x",
        chat_model="c",
        chat_provider="p",
        chat_role="standard",
        embedding_model="ollama/nomic-embed-text",
        embedding_provider="ollama",
        embedding_dimension=768,
        hyde_model="h",
        hyde_provider="p",
        hyde_role="light",
        rerank_model="r",
        rerank_provider="p",
        rerank_role="light",
    )
    svc = RetrievalService(RetrievalConfig(pair=pair))
    client = MagicMock()
    client.get_collection = AsyncMock(
        return_value=MagicMock(config=MagicMock(params=MagicMock(vectors=MagicMock(size=768))))
    )
    qdrant = MagicMock()
    qdrant.get_client.return_value = client

    with (
        patch("monitor_data.db.qdrant.QdrantClient", return_value=qdrant),
        patch.object(svc, "_get_meta", AsyncMock(return_value=None)),
    ):
        # Must NOT raise.
        await svc.ensure_collection("legacy_collection")


@pytest.mark.asyncio
async def test_ensure_collection_records_active_model_on_first_index():
    """index() writes the active pair's model to meta — that's what
    closes the legacy gap (the next ensure_collection will then have
    meta to check)."""
    from monitor_data.retrieval.embedder import Embedder
    from monitor_data.retrieval.pairs import ModelPair
    from monitor_data.retrieval.service import RetrievalService

    pair = ModelPair(
        name="x",
        chat_model="c",
        chat_provider="p",
        chat_role="standard",
        embedding_model="ollama/nomic-embed-text",
        embedding_provider="ollama",
        embedding_dimension=768,
        hyde_model="h",
        hyde_provider="p",
        hyde_role="light",
        rerank_model="r",
        rerank_provider="p",
        rerank_role="light",
    )
    svc = RetrievalService(RetrievalConfig(pair=pair))
    embedder = MagicMock(spec=Embedder)
    embedder.embed_batch = AsyncMock()
    svc._embedder = embedder  # type: ignore[assignment]
    client = MagicMock()
    client.get_collection = AsyncMock(
        return_value=MagicMock(config=MagicMock(params=MagicMock(vectors=MagicMock(size=768))))
    )
    client.upsert = AsyncMock()
    qdrant = MagicMock()
    qdrant.get_client.return_value = client

    recorded: dict = {}

    async def _set_meta(_collection, _model, _dimension):
        recorded["called"] = True

    embedder.embed_batch.return_value = [[0.1] * 768]

    with (
        patch("monitor_data.db.qdrant.QdrantClient", return_value=qdrant),
        patch.object(svc, "_get_meta", AsyncMock(return_value=None)),
        patch.object(svc, "_set_meta", _set_meta),
    ):
        await svc.index("legacy_collection", [Document(id="1", text="a")])

    assert recorded.get("called"), "index() must call _set_meta to close the legacy gap"


# ===========================================================================
# Phase 4 — Hermetic smoke: end-to-end wiring
# ===========================================================================
# Build a real Embedder + real PairLLM (mocked litellm) and exercise them
# through the RetrievalService surface. This catches wiring bugs that
# unit tests miss (e.g. forgetting to pass the pair to the constructor).
# ===========================================================================


@pytest.mark.asyncio
async def test_hermetic_smoke_service_uses_real_embedder_and_pair_llm():
    """Build a service with REAL Embedder + REAL PairLLM, mock only
    the litellm calls. Run a real ``retrieve()`` end-to-end."""
    from monitor_data.retrieval.config import RetrievalConfig
    from monitor_data.retrieval.embedder import Embedder
    from monitor_data.retrieval.pair_llm import PairLLM
    from monitor_data.retrieval.pairs import ModelPair
    from monitor_data.retrieval.service import RetrievalService

    pair = ModelPair(
        name="x",
        chat_model="c",
        chat_provider="p",
        chat_role="standard",
        embedding_model="ollama/nomic-embed-text",
        embedding_provider="ollama",
        embedding_dimension=3,
        hyde_model="ollama/qwen2.5:latest",
        hyde_provider="ollama",
        hyde_role="light",
        rerank_model="ollama/qwen2.5:latest",
        rerank_provider="ollama",
        rerank_role="light",
    )
    pg = MagicMock()
    pg.provider_get_by_role = AsyncMock(
        side_effect=lambda role: {
            "embedding": {
                "id": "e",
                "name": "e",
                "role": "embedding",
                "model": "ollama/nomic-embed-text",
                "provider": "ollama",
                "status": "connected",
                "api_key": "k",
                "base_url": "",
            },
            "light": {
                "id": "l",
                "name": "l",
                "role": "light",
                "model": "ollama/qwen2.5:latest",
                "provider": "ollama",
                "status": "connected",
                "api_key": "k",
                "base_url": "",
            },
        }[role]
    )
    pg.close = AsyncMock()

    svc = RetrievalService(RetrievalConfig(pair=pair))
    # Force the pair-validated config (skip the registry boot-block in
    # this smoke test — we already test that in other tests).
    svc._config = RetrievalConfig(pair=pair)
    # Build the real Embedder + real PairLLM with our mock pg.
    svc._embedder = Embedder(pair, pg=pg, preflight_enabled=False)
    svc._pair_llm = PairLLM(pair, pg=pg)

    # Mock only the litellm calls (the contract we're testing).
    captured_aembed: list = []
    acompl_calls: list = []

    async def _fake_aembed(**kwargs):
        captured_aembed.append(kwargs)
        return MagicMock(data=[{"embedding": [0.1, 0.2, 0.3]}])

    # HyDE returns the same query (avoid requiring a real rewrite).
    async def _fake_acompl(*args, **kwargs):
        acompl_calls.append(kwargs)
        return "q"

    with (
        patch("monitor_data.retrieval.embedder.litellm.aembedding", new=_fake_aembed),
        patch("monitor_data.retrieval.pair_llm.litellm.acompletion", new=_fake_acompl),
    ):
        # Run a real retrieve against a fake Qdrant.
        client = MagicMock()
        client.get_collection = AsyncMock(
            return_value=MagicMock(config=MagicMock(params=MagicMock(vectors=MagicMock(size=3))))
        )
        client.upsert = AsyncMock()

        # Patch _qdrant_search to return one hit.
        async def _fake_search(*_a, **_k):
            return [Hit(id="0", score=0.9, text="hit0", payload={})]

        svc._qdrant_search = _fake_search
        qdrant = MagicMock()
        qdrant.get_client.return_value = client
        with (
            patch("monitor_data.db.qdrant.QdrantClient", return_value=qdrant),
            patch.object(svc, "_get_meta", AsyncMock(return_value=None)),
            patch.object(svc, "_set_meta", AsyncMock()),
        ):
            # HyDE on (the pair enables it by default). Embed happens.
            await svc.retrieve("snippets", "the query", limit=1)

    # Embedder's litellm.aembedding was called (the single site).
    assert len(captured_aembed) == 1
    # PairLLM.acompletion was called (HyDE rewrite, then optionally rerank).
    assert len(acompl_calls) >= 1
    # The Embedder's model is the pair's, not anything else.
    assert captured_aembed[0]["model"] == "ollama/nomic-embed-text"
    # The first PairLLM call routed the HyDE prompt (the LLM call uses
    # all-kwargs, so we check the messages content for the query
    # substring + the max_tokens=200 marker that _hyde_rewrite passes).
    first_kwargs = acompl_calls[0]
    assert first_kwargs.get("max_tokens") == 200
    assert any("the query" in (m.get("content") or "") for m in first_kwargs.get("messages", []))
