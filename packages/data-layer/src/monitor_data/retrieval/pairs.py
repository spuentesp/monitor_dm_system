"""Model pair registry — the embedding gatekeeper's source of truth.

A registered ``ModelPair`` binds a chat LLM to an embedding model (and
its HyDE / rerank siblings) under a single named contract. The
``PairRegistry`` reads rows from the ``model_pairs`` Postgres table and
``validate_active_pair()`` is the single boot-blocking assertion that
the live ``llm_providers`` rows match an active pair. If they don't,
the system refuses to start — that's the gatekeeper's job.

Why this exists: the previous retrieval layer let any code call
``monitor_data.db.embeddings.embed_text`` and pick whatever model the
caller (or the env) wanted. We shipped a real bug because of it
(2026-07-20) — nomic-built Qdrant collection queried with gemini
embeddings. Same dim, so the model/dim guard didn't catch it. This
module is the answer: the LLM and embedding model are paired as one
contract; changing one without the other is a boot-time error.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from typing import Any

from monitor_data.db.postgres import PostgresClient

from .errors import IncompatiblePairError

# A registered pair has every value pinned — no env vars, no role-based
# resolution, no fall-back. The gatekeeper either matches exactly or
# refuses to start.
_VALID_STATUS = ("active", "deprecated", "disabled")
_VALID_ROLES = ("light", "standard", "heavy")


@dataclass(frozen=True)
class ModelPair:
    """One registered chat+embedding+hyde+rerank contract.

    All four components are pinned to a specific ``(model, provider)`` pair.
    The gatekeeper refuses to start unless the live ``llm_providers``
    rows for those four components match this row exactly.
    """

    name: str
    status: str = "active"
    chat_model: str = ""
    chat_provider: str = ""
    chat_role: str = "standard"
    embedding_model: str = ""
    embedding_provider: str = ""
    embedding_dimension: int = 0
    hyde_model: str = ""
    hyde_provider: str = ""
    hyde_role: str = "light"
    rerank_model: str = ""
    rerank_provider: str = ""
    rerank_role: str = "light"
    notes: str = ""

    def __post_init__(self) -> None:
        if self.status not in _VALID_STATUS:
            raise ValueError(f"ModelPair.status must be one of {_VALID_STATUS}, got {self.status!r}")
        for role_attr in ("chat_role", "hyde_role", "rerank_role"):
            v = getattr(self, role_attr)
            if v not in _VALID_ROLES:
                raise ValueError(f"ModelPair.{role_attr} must be one of {_VALID_ROLES}, got {v!r}")
        if self.embedding_dimension <= 0:
            raise ValueError(f"ModelPair.embedding_dimension must be > 0, got {self.embedding_dimension}")
        for field_name in (
            "chat_model",
            "chat_provider",
            "embedding_model",
            "embedding_provider",
            "hyde_model",
            "hyde_provider",
            "rerank_model",
            "rerank_provider",
        ):
            if not getattr(self, field_name):
                raise ValueError(f"ModelPair.{field_name} must be non-empty")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ModelPair:
        """Build from a dict, ignoring keys that aren't ModelPair fields.

        The Postgres row includes ``created_at`` / ``updated_at`` (and any
        future audit columns) that aren't part of the pair contract itself —
        filter to known field names so a raw DB row can be passed directly.
        """
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in known})


def _provider_matches_live(
    pair: ModelPair,
    *,
    role: str,
    model: str,
    provider: str,
) -> bool:
    """One component of the boot-time match check: does the registered
    pair's ``(model, provider)`` for ``role`` match the live row?"""
    if role == "chat":
        return model == pair.chat_model and provider == pair.chat_provider
    if role == "embedding":
        return model == pair.embedding_model and provider == pair.embedding_provider
    if role == "hyde":
        return model == pair.hyde_model and provider == pair.hyde_provider
    if role == "rerank":
        return model == pair.rerank_model and provider == pair.rerank_provider
    raise ValueError(f"unknown role: {role!r}")


class PairRegistry:
    """Reads ``model_pairs`` from Postgres and validates the live
    ``llm_providers`` rows against it.

    The single boot-blocking method is :meth:`validate_active_pair` —
    it raises :class:`IncompatiblePairError` on any mismatch, with a
    message that names the offending field so the operator can fix
    the row in one place.
    """

    def __init__(self, pg: PostgresClient | None = None) -> None:
        self._pg = pg

    async def _client(self) -> PostgresClient:
        if self._pg is not None:
            return self._pg
        return PostgresClient()

    async def active_pair(self) -> ModelPair | None:
        """Return the registered active pair, or None if none is active.

        The unique partial index on ``status='active'`` ensures at most
        one row returns; multiple active rows are a configuration
        error caught at insertion time.
        """
        client = await self._client()
        try:
            rows = await client.model_pair_list_active()
        finally:
            if self._pg is None:
                await client.close()
        if not rows:
            return None
        if len(rows) > 1:
            # Should be impossible thanks to the unique partial index;
            # if it happens the schema was tampered with manually.
            raise IncompatiblePairError(
                f"model_pairs has {len(rows)} active rows — expected exactly 1. "
                "Set all but one to status='deprecated' or 'disabled'."
            )
        return ModelPair.from_dict(rows[0])

    async def by_name(self, name: str) -> ModelPair | None:
        client = await self._client()
        try:
            row = await client.model_pair_get(name)
        finally:
            if self._pg is None:
                await client.close()
        if row is None:
            return None
        return ModelPair.from_dict(row)

    async def is_active_chat(self, model_name: str) -> bool:
        pair = await self.active_pair()
        return bool(pair and pair.chat_model == model_name)

    async def is_active_embedding(self, model_name: str) -> bool:
        pair = await self.active_pair()
        return bool(pair and pair.embedding_model == model_name)

    async def validate_active_pair(self) -> ModelPair:
        """The single boot-blocking assertion. Compares the active
        pair against the live ``llm_providers`` rows for chat /
        embedding / hyde / rerank roles. Raises
        :class:`IncompatiblePairError` on any mismatch.

        2026-07-22 centralization: validation now uses
        :meth:`PostgresClient.provider_list_by_role` and passes if
        **any** row for that role matches the pair's expected
        ``(model, provider)``. The default-only check used to fail
        the moment an operator flipped ``is_default`` at the DB level
        — making ``RetrievalConfig.resolve()`` a hostage to manual
        pair re-seeding. The default row is still logged as a hint
        (operators want to know which row the runtime will actually
        pick), but a non-default row that matches is also accepted.

        The runtime uses ``provider_get_by_role`` (default-only) when
        resolving at call time — so the auto-sync path in
        ``RetrievalConfig.resolve()`` keeps the pair aligned with the
        default. This validator's broader acceptance just stops the
        boot gate from blocking when the operator runs a local /
        non-default row.
        """
        pair = await self.active_pair()
        if pair is None:
            raise IncompatiblePairError(
                "no active model_pair is registered — the system cannot "
                "start without one. Insert a row with status='active' and "
                "matching chat/embedding/hyde/rerank values; see "
                "scripts/seed_ollama_embedding_provider.py for an example."
            )
        client = await self._client()

        mismatches: list[str] = []

        async def _check(role_key: str, pair_field_model: str, pair_field_provider: str) -> None:
            want_model = getattr(pair, pair_field_model)
            want_provider = getattr(pair, pair_field_provider)
            lookup_role = {
                "chat": pair.chat_role,
                "embedding": "embedding",
                "hyde": pair.hyde_role,
                "rerank": pair.rerank_role,
            }[role_key]
            live_rows = await client.provider_list_by_role(lookup_role)
            if not live_rows:
                mismatches.append(
                    f"{role_key}: pair says ({want_model!r}, {want_provider!r}) on "
                    f"role={lookup_role!r}, but no llm_providers row "
                    f"for that role exists."
                )
                return
            # Pass if ANY row for this role matches the pair's expected
            # (model, provider). The default row (rows[0]) is the one the
            # runtime will actually call — surfaced in the error message
            # so operators can see why the mismatch is failing.
            matched = any(
                _provider_matches_live(
                    pair,
                    role=role_key,
                    model=row.get("model") or "",
                    provider=row.get("provider") or "",
                )
                for row in live_rows
            )
            if not matched:
                default_row = live_rows[0]
                mismatches.append(
                    f"{role_key}: pair wants ({want_model!r}, {want_provider!r}); "
                    f"no llm_providers row with role={lookup_role!r} matches "
                    f"(default row is ({default_row.get('model')!r}, "
                    f"{default_row.get('provider')!r}); "
                    f"{len(live_rows)} row(s) exist for this role). "
                    f"Either update the pair row or insert/update a provider "
                    f"row that matches — do not change one without the other."
                )

        try:
            await _check("chat", "chat_model", "chat_provider")
            await _check("embedding", "embedding_model", "embedding_provider")
            await _check("hyde", "hyde_model", "hyde_provider")
            await _check("rerank", "rerank_model", "rerank_provider")
        finally:
            if self._pg is None:
                await client.close()

        if mismatches:
            raise IncompatiblePairError(
                "active model_pair is incompatible with live llm_providers:\n  - " + "\n  - ".join(mismatches)
            )
        return pair


# Public re-exports for ergonomics.
__all__ = ["IncompatiblePairError", "ModelPair", "PairRegistry"]
