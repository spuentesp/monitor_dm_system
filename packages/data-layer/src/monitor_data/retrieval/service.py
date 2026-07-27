"""RetrievalService — the single owner of embeddings + Qdrant retrieval.

Pair-driven: the embedding model + HyDE / rerank LLMs come from the
active :class:`ModelPair` (validated at boot by :class:`PairRegistry`).
The retrieval layer never reads the env, never falls back to settings,
never role-dispatches. Either the pair matches and the system runs, or
the system refuses to start.

The single :class:`Embedder` is the only place in the system that calls
``litellm.aembedding``; the single :class:`PairLLM` is the only place
that calls ``litellm.acompletion`` for retrieval. Both are constructed
once per process from the active pair.

LAYER: 1 (data-layer)
CALLED BY: agents (context_assembly, indexer, game_system routing), UI search
"""

from __future__ import annotations

import json
import logging
import math
from typing import Any

from monitor_data.db.postgres import PostgresClient
from monitor_data.retrieval.config import RetrievalConfig
from monitor_data.retrieval.contracts import (
    Document,
    EmbeddingModelMismatchError,
    Hit,
    Scored,
)
from monitor_data.retrieval.embedder import Embedder
from monitor_data.retrieval.pair_llm import PairLLM

logger = logging.getLogger(__name__)

# system_config key prefix for per-collection embedding-model metadata.
_META_KEY_PREFIX = "retrieval_meta:"

# Cap on cached candidate-vector sets (keyed by stable candidate lists in
# ``nearest``). Bounded by (game systems × candidate slots) in practice.
_CANDIDATE_CACHE_MAX = 256


def _cosine(a: list[float], b: list[float]) -> float:
    dot = na = nb = 0.0
    for x, y in zip(a, b, strict=False):
        dot += x * y
        na += x * x
        nb += y * y
    if na <= 0.0 or nb <= 0.0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))


class RetrievalService:
    """Owns embeddings + Qdrant. Construct once; ``await`` the async methods.

    The embedding model + retrieval LLMs come from the active
    :class:`ModelPair`. The service instantiates one :class:`Embedder`
    and one :class:`PairLLM` from that pair and routes every embed /
    HyDE / rerank call through them — no env, no role-dispatch, no
    settings fall-back.

    At the first call (or first :meth:`model` / :meth:`dimension` /
    :meth:`embed_query` / :meth:`embed_docs` / :meth:`retrieve` /
    :meth:`index` / :meth:`nearest` / :meth:`ensure_collection`), the
    service calls :meth:`RetrievalConfig.resolve`, which calls the
    :class:`PairRegistry`'s boot-blocking ``validate_active_pair``.
    The process refuses to start if no pair is active, or the live
    ``llm_providers`` rows don't match it.
    """

    def __init__(self, config: RetrievalConfig | None = None) -> None:
        self._config = config
        self._embedder: Embedder | None = None
        self._pair_llm: PairLLM | None = None
        # Collections whose model/dim guard already passed strictly this
        # process — skip the per-call Qdrant get_collection + Postgres
        # get_meta round trips on the hot path.
        self._verified: set[str] = set()
        # Cached candidate-vector sets for ``nearest(candidates_key=...)``.
        self._candidate_cache: dict[str, list[list[float]]] = {}

    async def _cfg(self) -> RetrievalConfig:
        if self._config is None:
            # Boot-blocking: the registry will raise IncompatiblePairError
            # if the live llm_providers rows don't match an active pair.
            self._config = await RetrievalConfig.resolve()
        return self._config

    async def _embedder_inst(self) -> Embedder:
        if self._embedder is None:
            cfg = await self._cfg()
            self._embedder = Embedder(cfg.pair)
        return self._embedder

    async def _pair_llm_inst(self) -> PairLLM:
        if self._pair_llm is None:
            cfg = await self._cfg()
            self._pair_llm = PairLLM(cfg.pair)
        return self._pair_llm

    # ------------------------------------------------------------------
    # Config accessors
    # ------------------------------------------------------------------

    async def model(self) -> str:
        return (await self._cfg()).embedding_model

    async def dimension(self) -> int:
        return (await self._cfg()).embedding_dimension

    # ------------------------------------------------------------------
    # Embedding — through the single Embedder
    # ------------------------------------------------------------------

    async def embed_query(self, text: str) -> list[float]:
        """Embed a single query with the pair's pinned model."""
        return await (await self._embedder_inst()).embed(text)

    async def embed_docs(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of documents with the pair's pinned model."""
        return await (await self._embedder_inst()).embed_batch(texts)

    # ------------------------------------------------------------------
    # Collection guard — the fail-loud model/dim consistency check
    # ------------------------------------------------------------------

    async def ensure_collection(self, collection: str, *, adopt: bool = False) -> None:
        """Ensure ``collection`` exists and matches the active embedding model.

        - Creates the collection (via the Qdrant client) if missing.
        - Hard-fails if the live Qdrant vector size != the pair's dim.
        - Hard-fails if a recorded model exists and differs from the active
          model (:class:`EmbeddingModelMismatchError`).
        - Warns (does not fail) when no model is recorded yet — legacy
          collections built before this service. ``index`` records the model
          on first write; a deliberate reindex adopts existing ones.

        ``adopt=True`` is the deliberate-reindex path: a recorded-model
        mismatch is downgraded to a warning instead of raising, because the
        caller is intentionally re-embedding the collection with the new
        pinned model (``index`` then rewrites the recorded model). The
        dimension check still hard-fails. Adopt calls bypass (and never
        populate) the strict-verification cache.
        """
        if not adopt and collection in self._verified:
            return

        cfg = await self._cfg()

        from monitor_data.db.qdrant import QdrantClient

        qdrant = QdrantClient()
        client = qdrant.get_client()

        # Create if missing.
        try:
            info = await client.get_collection(collection)
        except Exception:
            await qdrant.ensure_collection(collection)
            info = await client.get_collection(collection)

        live_dim = _collection_dim(info)
        if live_dim is not None and int(live_dim) != int(cfg.embedding_dimension):
            raise EmbeddingModelMismatchError(
                f"Collection '{collection}' has vector size {live_dim} but the active "
                f"embedding model '{cfg.embedding_model}' produces {cfg.embedding_dimension}-dim "
                f"vectors. Re-index the collection with the pinned model."
            )

        recorded = await self._get_meta(collection)
        if recorded is not None:
            recorded_model = recorded.get("model")
            if recorded_model and recorded_model != cfg.embedding_model:
                if adopt:
                    logger.warning(
                        "retrieval: adopting collection '%s' from model '%s' to '%s' (deliberate reindex).",
                        collection,
                        recorded_model,
                        cfg.embedding_model,
                    )
                else:
                    raise EmbeddingModelMismatchError(
                        f"Collection '{collection}' was built with embedding model "
                        f"'{recorded_model}', but the active model is '{cfg.embedding_model}'. "
                        f"Querying it would return garbage. Re-index or restore the "
                        f"correct embedding provider."
                    )
        else:
            logger.warning(
                "retrieval: collection '%s' has no recorded embedding model "
                "(legacy). Active model is '%s'. Run a reindex to record it.",
                collection,
                cfg.embedding_model,
            )

        if not adopt:
            self._verified.add(collection)

    # ------------------------------------------------------------------
    # Indexing — embed docs, upsert, record the model
    # ------------------------------------------------------------------

    async def index(self, collection: str, docs: list[Document], *, adopt: bool = False) -> None:
        """Embed ``docs`` with the pinned model and upsert them into ``collection``.

        Records the active embedding model for the collection so future
        ``ensure_collection`` calls can detect a model mismatch.
        """
        if not docs:
            return
        await self.ensure_collection(collection, adopt=adopt)

        vectors = await self.embed_docs([d.text for d in docs])

        from monitor_data.db.qdrant import QdrantClient

        qdrant = QdrantClient()
        client = qdrant.get_client()

        from qdrant_client.models import PointStruct

        points = [
            PointStruct(id=d.id, vector=vec, payload={**d.payload, "text": d.text})
            for d, vec in zip(docs, vectors, strict=False)
        ]
        await client.upsert(collection_name=collection, points=points)

        cfg = await self._cfg()
        await self._set_meta(collection, cfg.embedding_model, cfg.embedding_dimension)
        self._verified.add(collection)

    # ------------------------------------------------------------------
    # Retrieval + nearest
    # ------------------------------------------------------------------

    async def retrieve(
        self,
        collection: str,
        query: str,
        *,
        filters: dict[str, Any] | None = None,
        limit: int = 10,
        rewrite: bool | None = None,
        rerank: bool | None = None,
    ) -> list[Hit]:
        """Retrieve the ``limit`` most relevant points for ``query``.

        Flow: (optional HyDE rewrite via the single PairLLM) → embed
        with the pair's model → Qdrant nearest-vector search → (optional
        LLM rerank via the same PairLLM) → hits. ``rewrite`` / ``rerank``
        default to the config toggles; pass False on latency-sensitive
        paths.

        HyDE + rerank fail SOFT — on PairLLMProviderError we fall back to
        plain vector search, which is still correct. The embedding step
        fails loud (EmbedderProviderError → no fake vectors).
        """
        cfg = await self._cfg()
        await self.ensure_collection(collection)

        do_rewrite = cfg.enable_hyde if rewrite is None else rewrite
        do_rerank = cfg.enable_rerank if rerank is None else rerank

        pair_llm = await self._pair_llm_inst() if (do_rewrite or do_rerank) else None

        # 1. HyDE rewrite (optional) — embed a hypothetical answer, not the query.
        embed_input = query
        if do_rewrite:
            try:
                if pair_llm:
                    embed_input = await _hyde_rewrite(pair_llm, query)
            except Exception as exc:
                logger.info("retrieve.hyde_failed (%s); using raw query", exc)
                embed_input = query

        # 2. Embed (fail loud) with the pair's model.
        vec = await self.embed_query(embed_input)

        # 3. Qdrant nearest — fetch extra when reranking so the reranker has
        #    candidates to reorder.
        fetch = limit * 3 if do_rerank else limit
        hits = await self._qdrant_search(collection, vec, filters=filters, limit=fetch)

        # 4. Rerank (optional, fail soft).
        if do_rerank and hits:
            try:
                if pair_llm:
                    hits = await _llm_rerank(pair_llm, query, hits, top_k=limit)
            except Exception as exc:
                logger.info("retrieve.rerank_failed (%s); using vector order", exc)
                hits = hits[:limit]
        else:
            hits = hits[:limit]

        return hits

    async def nearest(
        self,
        query: str,
        candidates: list[str],
        *,
        top_k: int = 1,
        candidates_key: str | None = None,
    ) -> list[Scored]:
        """Rank ``candidates`` by cosine similarity to ``query`` (in-process, no Qdrant)."""
        indexed = [(i, c) for i, c in enumerate(candidates) if c and c.strip()]
        if not (query or "").strip() or not indexed:
            return []
        cand_texts = [c for _, c in indexed]

        if candidates_key is None:
            vectors = await self.embed_docs([query, *cand_texts])
            qvec, cand_vecs = vectors[0], vectors[1:]
        else:
            cand_vecs = self._candidate_cache.get(candidates_key) or []
            if cand_vecs is None or len(cand_vecs) != len(cand_texts):
                cand_vecs = await self.embed_docs(cand_texts)
                if len(self._candidate_cache) >= _CANDIDATE_CACHE_MAX:
                    self._candidate_cache.clear()
                self._candidate_cache[candidates_key] = cand_vecs
            qvec = await self.embed_query(query)

        scored = [
            Scored(candidate=indexed[j][1], index=indexed[j][0], score=_cosine(qvec, cand_vec))
            for j, cand_vec in enumerate(cand_vecs)
        ]
        scored.sort(key=lambda s: s.score, reverse=True)
        return scored[: max(1, top_k)]

    async def _qdrant_search(
        self,
        collection: str,
        vector: list[float],
        *,
        filters: dict[str, Any] | None = None,
        limit: int = 10,
    ) -> list[Hit]:
        from monitor_data.db.qdrant import QdrantClient
        from monitor_data.tools.qdrant_tools import _qdrant_search_points

        qdrant = QdrantClient()
        client = qdrant.get_client()
        query_filter = _build_filter(filters)
        points = await _qdrant_search_points(
            client,
            collection_name=collection,
            query_vector=vector,
            limit=limit,
            query_filter=query_filter,
            score_threshold=None,
        )
        hits: list[Hit] = []
        for p in points:
            payload = getattr(p, "payload", None) or {}
            hits.append(
                Hit(
                    id=str(getattr(p, "id", "")),
                    score=float(getattr(p, "score", 0.0) or 0.0),
                    payload=dict(payload),
                    text=payload.get("text"),
                )
            )
        return hits

    # ------------------------------------------------------------------
    # Meta store — per-collection embedding model, kept in system_config
    # ------------------------------------------------------------------

    async def _get_meta(self, collection: str) -> dict[str, Any] | None:
        try:
            pg = PostgresClient()
            raw = await pg.config_get(f"{_META_KEY_PREFIX}{collection}")
            return json.loads(raw) if raw else None
        except Exception as exc:
            logger.debug("retrieval: could not read meta for '%s': %s", collection, exc)
            return None

    async def _set_meta(self, collection: str, model: str, dimension: int) -> None:
        try:
            pg = PostgresClient()
            await pg.config_set(
                f"{_META_KEY_PREFIX}{collection}",
                json.dumps({"model": model, "dimension": dimension}),
            )
        except Exception as exc:
            logger.warning("retrieval: could not record meta for '%s': %s", collection, exc)


# ---------------------------------------------------------------------------
# HyDE / rerank helpers — thin wrappers over the single PairLLM
# ---------------------------------------------------------------------------

_HYDE_PROMPT = (
    "You are helping a retrieval system. Given a user's question or query, write a "
    "short, plausible passage (2-4 sentences) that would appear in a document that "
    "directly answers it. Write it as if it were the answer text itself, not a "
    "description of the answer. Do not preface it.\n\nQuery: {query}\n\nPassage:"
)


async def _hyde_rewrite(pair_llm: PairLLM, query: str) -> str:
    text = await pair_llm.acompletion("hyde", _HYDE_PROMPT.format(query=query), max_tokens=200)
    return text or query


_RERANK_PROMPT = (
    "Rate how relevant each numbered passage is to the query, 0 (irrelevant) to "
    "10 (directly answers it). Respond with ONLY a comma-separated list of "
    "integers, one per passage, in order. No other text.\n\n"
    "Query: {query}\n\n{passages}\n\nScores:"
)


def _parse_scores(text: str, n: int) -> list[float]:
    """Parse the LLM's comma/newline-separated integer scores.

    Coerce to known len by padding/truncating with 0.0 (legacy behavior).
    """
    parts = [p.strip() for p in text.replace("\n", ",").split(",") if p.strip()]
    scores: list[float] = []
    for p in parts:
        try:
            scores.append(float(p))
        except ValueError:
            continue
    if len(scores) < n:
        scores += [0.0] * (n - len(scores))
    return scores[:n]


async def _llm_rerank(pair_llm: PairLLM, query: str, hits: list[Hit], *, top_k: int) -> list[Hit]:
    passages = "\n".join(f"[{i}] {(h.text or str(h.payload))[:400]}" for i, h in enumerate(hits))
    raw = await pair_llm.acompletion("rerank", _RERANK_PROMPT.format(query=query, passages=passages), max_tokens=64)
    scores = _parse_scores(raw, len(hits))
    ranked = sorted(zip(hits, scores, strict=False), key=lambda hs: hs[1], reverse=True)
    return [h for h, _ in ranked[:top_k]]


# ---------------------------------------------------------------------------
# Filters + helpers
# ---------------------------------------------------------------------------


def _build_filter(filters: dict[str, Any] | None) -> Any:
    if not filters:
        return None
    from qdrant_client.models import FieldCondition, Filter, MatchAny, MatchValue

    conditions = []
    for key, value in filters.items():
        if value is None:
            continue
        if isinstance(value, (list, tuple, set)):
            conditions.append(FieldCondition(key=key, match=MatchAny(any=list(value))))
        else:
            conditions.append(FieldCondition(key=key, match=MatchValue(value=value)))
    return Filter(must=conditions) if conditions else None


def _collection_dim(info: Any) -> int | None:
    try:
        vectors = info.config.params.vectors
        if hasattr(vectors, "size"):
            return int(vectors.size)
        if isinstance(vectors, dict) and vectors:
            first = next(iter(vectors.values()))
            return int(getattr(first, "size", 0)) or None
    except Exception:
        return None
    return None


# ---------------------------------------------------------------------------
# Process-wide singleton
# ---------------------------------------------------------------------------

_SERVICE: RetrievalService | None = None


def default_retrieval_service() -> RetrievalService:
    """Process-wide singleton so the pair is resolved once."""
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = RetrievalService()
    return _SERVICE


def reset_retrieval_service() -> None:
    """Drop the singleton (tests + config reloads)."""
    global _SERVICE
    _SERVICE = None
