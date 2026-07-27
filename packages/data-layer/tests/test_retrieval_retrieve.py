"""
Tests for RetrievalService.retrieve() + nearest() (P2).

Covers:
- retrieve() flow: HyDE rewrite -> embed -> qdrant search -> rerank.
- HyDE fail-soft: LLM error falls back to the raw query.
- rerank fail-soft: LLM error falls back to vector order.
- rewrite/rerank per-call toggles.
- nearest(): in-process cosine ranking maps winner back to input index.

Hermetic — embeddings, Qdrant search, and the single PairLLM are
stubbed. The RetrievalConfig is built from a fixed ModelPair (the
"vtm5-flash-nomic" pattern); the gatekeeper's boot-time check is
covered in test_retrieval_pair_contract.py, not here.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from monitor_data.retrieval import (
    Hit,
    RetrievalConfig,
    RetrievalService,
    reset_retrieval_service,
)
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
    # Split: ModelPair takes model/dim/role kwargs, RetrievalConfig takes toggles.
    pair_kwargs = {k: v for k, v in kw.items() if k in {"embedding_model", "embedding_dimension"}}
    pair = _sample_pair(**pair_kwargs)
    return RetrievalConfig(
        pair=pair,
        enable_hyde=kw.get("enable_hyde", True),
        enable_rerank=kw.get("enable_rerank", True),
    )


def _service_with_search(hits, cfg=None):
    """Build a RetrievalService whose ensure_collection + qdrant search are stubbed."""
    svc = RetrievalService(cfg or _cfg())

    async def _noop_ensure(_collection):
        return None

    async def _fake_search(collection, vector, *, filters=None, limit=10):
        return hits[:limit]

    svc.ensure_collection = _noop_ensure  # type: ignore[assignment]
    svc._qdrant_search = _fake_search  # type: ignore[assignment]
    return svc


# ============================================================================
# retrieve() flow
# ============================================================================


@pytest.mark.asyncio
async def test_retrieve_runs_hyde_embed_search_rerank_in_order():
    hits = [Hit(id=str(i), score=1.0 - i * 0.1, text=f"passage {i}") for i in range(5)]
    svc = _service_with_search(hits, _cfg(enable_hyde=True, enable_rerank=True))

    calls = []
    pair_llm = MagicMock()

    async def _fake_hyde(_query, _pl):
        calls.append("hyde")
        return "hypothetical answer"

    async def _fake_embed(text):
        calls.append(("embed", text))
        return [0.1] * 768

    async def _fake_rerank(*_a, **_k):
        calls.append("rerank")
        # Reverse order to prove rerank actually reorders.
        return list(reversed(hits))[:3]

    pair_llm.acompletion = AsyncMock(side_effect=_fake_rerank)
    # hyde_rewrite is a module-level function in service.py — patch there.
    with (
        patch.object(svc, "_pair_llm_inst", AsyncMock(return_value=pair_llm)),
        patch("monitor_data.retrieval.service._hyde_rewrite", _fake_hyde),
        patch.object(svc, "embed_query", _fake_embed),
    ):
        out = await svc.retrieve("snippets", "what is the thing?", limit=3)

    # HyDE ran, then embed used the HyDE passage, then rerank ran.
    assert "hyde" in calls
    assert ("embed", "hypothetical answer") in calls
    assert "rerank" in calls
    assert len(out) == 3


@pytest.mark.asyncio
async def test_retrieve_without_rerank_returns_vector_order():
    hits = [Hit(id=str(i), score=1.0 - i * 0.1, text=f"p{i}") for i in range(5)]
    svc = _service_with_search(hits, _cfg(enable_hyde=False, enable_rerank=False))

    async def _fake_embed(text):
        return [0.1] * 768

    with patch.object(svc, "embed_query", _fake_embed):
        out = await svc.retrieve("snippets", "q", limit=3, rewrite=False, rerank=False)

    # Vector order preserved, truncated to limit.
    assert [h.id for h in out] == ["0", "1", "2"]


@pytest.mark.asyncio
async def test_retrieve_hyde_fail_soft_uses_raw_query():
    """If HyDE errors, retrieve embeds the raw query, not crash."""
    hits = [Hit(id="0", score=0.9, text="p")]
    svc = _service_with_search(hits, _cfg(enable_hyde=True, enable_rerank=False))

    embedded = {}

    async def _fake_embed(text):
        embedded["text"] = text
        return [0.1] * 768

    pair_llm = MagicMock()

    async def _hyde_boom(*_a, **_k):
        raise RuntimeError("LLM down")

    pair_llm.acompletion = AsyncMock(side_effect=_hyde_boom)

    with (
        patch.object(svc, "_pair_llm_inst", AsyncMock(return_value=pair_llm)),
        patch(
            "monitor_data.retrieval.service._hyde_rewrite",
            AsyncMock(side_effect=_hyde_boom),
        ),
        patch.object(svc, "embed_query", _fake_embed),
    ):
        await svc.retrieve("snippets", "raw query text", limit=1)

    assert embedded["text"] == "raw query text"


@pytest.mark.asyncio
async def test_retrieve_rerank_fail_soft_uses_vector_order():
    hits = [Hit(id=str(i), score=1.0 - i * 0.1, text=f"p{i}") for i in range(4)]
    svc = _service_with_search(hits, _cfg(enable_hyde=False, enable_rerank=True))

    async def _fake_embed(text):
        return [0.1] * 768

    pair_llm = MagicMock()

    async def _rerank_boom(*_a, **_k):
        raise RuntimeError("LLM down")

    pair_llm.acompletion = AsyncMock(side_effect=_rerank_boom)

    with (
        patch.object(svc, "_pair_llm_inst", AsyncMock(return_value=pair_llm)),
        patch.object(svc, "embed_query", _fake_embed),
    ):
        out = await svc.retrieve("snippets", "q", limit=2)

    # Rerank failed -> vector order preserved.
    assert [h.id for h in out] == ["0", "1"]


# ============================================================================
# nearest()
# ============================================================================


@pytest.mark.asyncio
async def test_nearest_ranks_by_cosine_and_maps_index():
    svc = RetrievalService(_cfg())

    # Query embeds to [1,0]; candidates: "brawl" close to query, "persuade" far.
    async def _fake_embed_docs(texts):
        table = {
            "I punch the guard": [1.0, 0.0],
            "Brawl: unarmed combat": [0.95, 0.05],
            "Persuade: sway with words": [0.0, 1.0],
        }
        return [table[t] for t in texts]

    with patch.object(svc, "embed_docs", _fake_embed_docs):
        out = await svc.nearest(
            "I punch the guard",
            ["Brawl: unarmed combat", "Persuade: sway with words"],
            top_k=2,
        )

    assert out[0].candidate == "Brawl: unarmed combat"
    assert out[0].index == 0
    assert out[0].score > out[1].score


@pytest.mark.asyncio
async def test_nearest_empty_inputs():
    svc = RetrievalService(_cfg())
    assert await svc.nearest("", ["a"], top_k=1) == []
    assert await svc.nearest("q", [], top_k=1) == []
