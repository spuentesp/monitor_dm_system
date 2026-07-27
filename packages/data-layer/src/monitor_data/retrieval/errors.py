"""Errors for the retrieval gatekeeper (Phase 2 of the embedding refactor).

These are the three contract errors the system raises when the
chat/embedding/HyDE/rerank pair contract is broken or the providers
fail. All three are fail-loud — never swallowed, never faked.
"""


class IncompatiblePairError(RuntimeError):
    """Boot-blocking: the live ``llm_providers`` rows don't match any
    registered pair (or no pair is registered).

    Refusing to start is the contract. The system used to silently
    poison its Qdrant collection by indexing with model A and querying
    with model B; the gatekeeper now refuses to run in that state.
    """


class EmbedderProviderError(RuntimeError):
    """The single Embedder failed to produce a vector (provider error,
    empty response, no key, network). Fail-loud: never fakes a vector,
    never falls back to a zero-dim or hash placeholder.

    Replaces the old ``EmbeddingProviderError`` that lived in the
    deleted ``monitor_data.db.embeddings`` module.
    """


class EmbeddingModelMissingError(RuntimeError):
    """The live provider is reachable but does not have the configured
    embedding model loaded/pulled (e.g. ``nomic-embed-text:latest`` not in
    the local Ollama registry). The operator must run ``ollama pull`` or
    switch the pair's ``embedding_model``.

    Independent exception — *not* a subclass of
    :class:`EmbedderProviderError` — so a real provider outage is
    distinguishable from an operator misconfiguration. Callers that want
    to handle both should catch ``(EmbeddingModelMissingError,
    EmbedderProviderError)`` explicitly.
    """


class PairLLMProviderError(RuntimeError):
    """The single PairLLM failed to produce a completion (HyDE rewrite,
    rerank prompt). Fail-loud: never fakes a completion.
    """
