"""
Tests for the RetrievalService (pair-driven).

The service no longer reads env vars or role-dispatches; it pulls the
chat/embedding/hyde/rerank tuple from the active :class:`ModelPair`.
These tests cover the service's behavior given a resolved pair:

- embed_query / embed_docs route through the single Embedder.
- ensure_collection guard: hard-fail on dim mismatch and on model
  mismatch, warn (not fail) on missing meta, dim mismatch hard-fails
  even under adopt.
- index records the model in the meta store; adopt rewrites the
  recorded model from the active pair.
- Strict-verification cache short-circuits the second guard call.
- nearest(candidates_key=...) caches the candidate vectors so the
  candidate list embeds once.

Hermetic — the Embedder is patched at the instance level. Boot-time
pair validation is covered in test_retrieval_pair_contract.py.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from monitor_data.retrieval import (
    Document,
    EmbeddingModelMismatchError,
    RetrievalConfig,
    RetrievalService,
    reset_retrieval_service,
)
from monitor_data.retrieval.embedder import Embedder
from monitor_data.retrieval.pairs import ModelPair


@pytest.fixture(autouse=True)
def _reset():
    reset_retrieval_service()
    yield
    reset_retrieval_service()


def _sample_pair(**overrides) -> ModelPair:
    base = {
        "name": "vtm5-flash-nomic",
        "chat_model": "gemini-2.5-flash",
        "chat_provider": "google_ai_studio",
        "chat_role": "standard",
        "embedding_model": "ollama/nomic-embed-text",
        "embedding_provider": "ollama",
        "embedding_dimension": 768,
        "hyde_model": "ollama/qwen2.5:latest",
        "hyde_provider": "ollama",
        "hyde_role": "light",
        "rerank_model": "ollama/qwen2.5:latest",
        "rerank_provider": "ollama",
        "rerank_role": "light",
    }
    base.update(overrides)
    return ModelPair(**base)


def _cfg(**kw) -> RetrievalConfig:
    pair = _sample_pair(**kw)
    return RetrievalConfig(
        pair=pair,
        enable_hyde=kw.get("enable_hyde", True),
        enable_rerank=kw.get("enable_rerank", True),
    )


def _service_with_embedder(
    cfg: RetrievalConfig | None = None,
) -> tuple[RetrievalService, MagicMock]:
    """Build a service with a stubbed Embedder. Returns (svc, embedder_mock)."""
    svc = RetrievalService(cfg or _cfg())
    embedder = MagicMock(spec=Embedder)
    embedder.embed = AsyncMock()
    embedder.embed_batch = AsyncMock()
    svc._embedder = embedder  # type: ignore[assignment]
    return svc, embedder


# ============================================================================
# Embedding — through the single Embedder
# ============================================================================


@pytest.mark.asyncio
async def test_embed_query_delegates_to_embedder():
    svc, embedder = _service_with_embedder()
    embedder.embed.return_value = [0.1, 0.2, 0.3]
    out = await svc.embed_query("hello")
    assert out == [0.1, 0.2, 0.3]
    embedder.embed.assert_awaited_once_with("hello")


@pytest.mark.asyncio
async def test_embed_docs_delegates_to_embedder_batch():
    svc, embedder = _service_with_embedder()
    embedder.embed_batch.return_value = [[0.1], [0.2]]
    out = await svc.embed_docs(["a", "b"])
    assert out == [[0.1], [0.2]]
    embedder.embed_batch.assert_awaited_once_with(["a", "b"])


@pytest.mark.asyncio
async def test_model_and_dimension_read_pair():
    svc = RetrievalService(_cfg(embedding_model="ollama/nomic-embed-text", embedding_dimension=768))
    assert await svc.model() == "ollama/nomic-embed-text"
    assert await svc.dimension() == 768


# ============================================================================
# ensure_collection guard
# ============================================================================


def _qdrant_info(dim: int):
    info = MagicMock()
    info.config.params.vectors.size = dim
    return info


@pytest.mark.asyncio
async def test_ensure_collection_dim_mismatch_fails_loud():
    svc = RetrievalService(_cfg(embedding_dimension=768))
    client = MagicMock()
    client.get_collection = AsyncMock(return_value=_qdrant_info(3072))  # gemini dim
    qdrant = MagicMock()
    qdrant.get_client.return_value = client
    qdrant.ensure_collection = AsyncMock()

    with patch("monitor_data.db.qdrant.QdrantClient", return_value=qdrant):
        with pytest.raises(EmbeddingModelMismatchError):
            await svc.ensure_collection("snippets")


@pytest.mark.asyncio
async def test_ensure_collection_model_mismatch_fails_loud():
    svc = RetrievalService(_cfg(embedding_model="ollama/nomic-embed-text", embedding_dimension=768))
    client = MagicMock()
    client.get_collection = AsyncMock(return_value=_qdrant_info(768))  # dim matches
    qdrant = MagicMock()
    qdrant.get_client.return_value = client
    qdrant.ensure_collection = AsyncMock()

    async def _get_meta(_collection):
        return {"model": "gemini/gemini-embedding-001", "dimension": 768}

    with (
        patch("monitor_data.db.qdrant.QdrantClient", return_value=qdrant),
        patch.object(svc, "_get_meta", _get_meta),
        pytest.raises(EmbeddingModelMismatchError),
    ):
        await svc.ensure_collection("snippets")


@pytest.mark.asyncio
async def test_ensure_collection_missing_meta_warns_not_fails(caplog):
    svc = RetrievalService(_cfg(embedding_model="ollama/nomic-embed-text", embedding_dimension=768))
    client = MagicMock()
    client.get_collection = AsyncMock(return_value=_qdrant_info(768))
    qdrant = MagicMock()
    qdrant.get_client.return_value = client
    qdrant.ensure_collection = AsyncMock()

    async def _no_meta(_collection):
        return None

    with (
        patch("monitor_data.db.qdrant.QdrantClient", return_value=qdrant),
        patch.object(svc, "_get_meta", _no_meta),
    ):
        # Must NOT raise — legacy collections warn, then a reindex records the model.
        await svc.ensure_collection("snippets")


@pytest.mark.asyncio
async def test_ensure_collection_matching_model_passes():
    svc = RetrievalService(_cfg(embedding_model="ollama/nomic-embed-text", embedding_dimension=768))
    client = MagicMock()
    client.get_collection = AsyncMock(return_value=_qdrant_info(768))
    qdrant = MagicMock()
    qdrant.get_client.return_value = client
    qdrant.ensure_collection = AsyncMock()

    async def _get_meta(_collection):
        return {"model": "ollama/nomic-embed-text", "dimension": 768}

    with (
        patch("monitor_data.db.qdrant.QdrantClient", return_value=qdrant),
        patch.object(svc, "_get_meta", _get_meta),
    ):
        await svc.ensure_collection("snippets")  # no raise


# ============================================================================
# index records the model
# ============================================================================


@pytest.mark.asyncio
async def test_index_records_model_meta():
    svc, embedder = _service_with_embedder()
    client = MagicMock()
    client.get_collection = AsyncMock(return_value=_qdrant_info(768))
    client.upsert = AsyncMock()
    qdrant = MagicMock()
    qdrant.get_client.return_value = client
    qdrant.ensure_collection = AsyncMock()

    recorded = {}

    async def _set_meta(collection, model, dimension):
        recorded[collection] = {"model": model, "dimension": dimension}

    async def _get_meta(_collection):
        return None

    embedder.embed_batch.return_value = [[0.1] * 768, [0.2] * 768]

    with (
        patch("monitor_data.db.qdrant.QdrantClient", return_value=qdrant),
        patch.object(svc, "_set_meta", _set_meta),
        patch.object(svc, "_get_meta", _get_meta),
    ):
        await svc.index(
            "snippets",
            [Document(id="1", text="a"), Document(id="2", text="b")],
        )

    assert client.upsert.called
    assert recorded["snippets"]["model"] == "ollama/nomic-embed-text"
    assert recorded["snippets"]["dimension"] == 768


# ============================================================================
# adopt=True — the deliberate-reindex path
# ============================================================================


@pytest.mark.asyncio
async def test_ensure_collection_adopt_downgrades_model_mismatch_to_warning():
    """With adopt=True, a recorded-model mismatch warns instead of raising."""
    svc = RetrievalService(_cfg(embedding_model="ollama/nomic-embed-text", embedding_dimension=768))
    client = MagicMock()
    client.get_collection = AsyncMock(return_value=_qdrant_info(768))
    qdrant = MagicMock()
    qdrant.get_client.return_value = client
    qdrant.ensure_collection = AsyncMock()

    async def _get_meta(_collection):
        return {"model": "gemini/gemini-embedding-001", "dimension": 768}

    with (
        patch("monitor_data.db.qdrant.QdrantClient", return_value=qdrant),
        patch.object(svc, "_get_meta", _get_meta),
    ):
        # No raise — the reindex is deliberately re-embedding with the new model.
        await svc.ensure_collection("snippets", adopt=True)


@pytest.mark.asyncio
async def test_ensure_collection_adopt_still_hard_fails_on_dim_mismatch():
    """adopt relaxes the model check but NOT the dimension check."""
    svc = RetrievalService(_cfg(embedding_dimension=768))
    client = MagicMock()
    client.get_collection = AsyncMock(return_value=_qdrant_info(3072))
    qdrant = MagicMock()
    qdrant.get_client.return_value = client
    qdrant.ensure_collection = AsyncMock()

    with patch("monitor_data.db.qdrant.QdrantClient", return_value=qdrant):
        with pytest.raises(EmbeddingModelMismatchError):
            await svc.ensure_collection("snippets", adopt=True)


@pytest.mark.asyncio
async def test_index_adopt_rewrites_stale_model_meta():
    """index(adopt=True) re-embeds and rewrites the recorded model — no raise."""
    svc, embedder = _service_with_embedder(_cfg(embedding_model="ollama/nomic-embed-text", embedding_dimension=768))
    client = MagicMock()
    client.get_collection = AsyncMock(return_value=_qdrant_info(768))
    client.upsert = AsyncMock()
    qdrant = MagicMock()
    qdrant.get_client.return_value = client
    qdrant.ensure_collection = AsyncMock()

    recorded = {"model": "gemini/gemini-embedding-001", "dimension": 768}

    async def _get_meta(_collection):
        return dict(recorded)

    async def _set_meta(collection, model, dimension):
        recorded.update(model=model, dimension=dimension)

    embedder.embed_batch.return_value = [[0.1] * 768]

    with (
        patch("monitor_data.db.qdrant.QdrantClient", return_value=qdrant),
        patch.object(svc, "_get_meta", _get_meta),
        patch.object(svc, "_set_meta", _set_meta),
    ):
        await svc.index("snippets", [Document(id="1", text="a")], adopt=True)

    # The stale gemini meta was rewritten to the active nomic model.
    assert recorded["model"] == "ollama/nomic-embed-text"


# ============================================================================
# ensure_collection strict-verification cache (guard I/O not on hot path)
# ============================================================================


@pytest.mark.asyncio
async def test_ensure_collection_caches_strict_pass():
    """A second strict ensure_collection skips the Qdrant/meta round trips."""
    svc = RetrievalService(_cfg(embedding_model="ollama/nomic-embed-text", embedding_dimension=768))
    client = MagicMock()
    client.get_collection = AsyncMock(return_value=_qdrant_info(768))
    qdrant = MagicMock()
    qdrant.get_client.return_value = client
    qdrant.ensure_collection = AsyncMock()

    meta_calls = {"n": 0}

    async def _get_meta(_collection):
        meta_calls["n"] += 1
        return {"model": "ollama/nomic-embed-text", "dimension": 768}

    with (
        patch("monitor_data.db.qdrant.QdrantClient", return_value=qdrant),
        patch.object(svc, "_get_meta", _get_meta),
    ):
        await svc.ensure_collection("snippets")
        await svc.ensure_collection("snippets")

    assert client.get_collection.await_count == 1  # second call short-circuits
    assert meta_calls["n"] == 1


# ============================================================================
# nearest candidates_key cache (regression: stable candidate lists embed once)
# ============================================================================


@pytest.mark.asyncio
async def test_nearest_candidates_key_caches_candidate_vectors():
    """With candidates_key set, candidates embed once; only the query re-embeds."""
    svc, embedder = _service_with_embedder(_cfg(embedding_dimension=3))
    candidates = ["climb the wall", "persuade the guard"]

    docs_calls: list[list[str]] = []

    async def _fake_embed_docs(texts):
        docs_calls.append(list(texts))
        return [[1.0, 0.0, 0.0] for _ in texts]

    async def _fake_embed_query(text):
        return [1.0, 0.0, 0.0]

    embedder.embed_batch.side_effect = _fake_embed_docs
    embedder.embed.side_effect = _fake_embed_query

    await svc.nearest("q1", candidates, top_k=1, candidates_key="k")
    await svc.nearest("q2", candidates, top_k=1, candidates_key="k")

    # embed_batch called exactly once (candidates cached); the second turn only
    # embedded the query.
    assert len(docs_calls) == 1
    assert docs_calls[0] == candidates


# ============================================================================
# _pair_llm_inst — single instantiation, lazy
# ============================================================================


@pytest.mark.asyncio
async def test_pair_llm_is_instantiated_lazily():
    """The service builds a single PairLLM on first use and reuses it."""
    svc = RetrievalService(_cfg())
    # Stub PairLLM at the module-import site so we can count constructions.
    with patch("monitor_data.retrieval.service.PairLLM") as pl_cls:
        pl_inst = MagicMock()
        pl_inst.acompletion = AsyncMock(return_value="hyde")
        pl_cls.return_value = pl_inst
        a = await svc._pair_llm_inst()
        b = await svc._pair_llm_inst()
    # One construction, same instance reused.
    assert pl_cls.call_count == 1
    assert a is b
