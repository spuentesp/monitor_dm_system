"""RetrievalConfig — the pair-driven retrieval config.

The whole retrieval subsystem commits to ONE registered pair (chat LLM +
embedding model + HyDE + rerank siblings). The active pair is the single
source of truth — there is no env-var precedence, no settings fallback,
no role-based dispatch. The pair is what :class:`PairRegistry` returns
after validating it against the live ``llm_providers`` rows.

The dimension is read from the pair (``pair.embedding_dimension``) and
cross-checked against the recorded Qdrant meta on ``ensure_collection``
so a model swap that changes dimension fails loud.

Toggles (``enable_hyde`` / ``enable_rerank``) are still env-driven — they
are *behavior* switches, not model pins. The pair pins the model; the
env toggles whether to use the model at all.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from monitor_data.db.postgres import PostgresClient

from .errors import IncompatiblePairError
from .pair_sync import sync_active_pair_from_defaults
from .pairs import ModelPair, PairRegistry


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


@dataclass
class RetrievalConfig:
    """Resolved retrieval configuration. Build via :meth:`resolve`.

    The four (model, provider) pairs come from the active
    :class:`ModelPair`. ``api_key`` / ``base_url`` are NOT stored on the
    config — they're read live from the matching ``llm_providers`` row
    by the Embedder / PairLLM.
    """

    pair: ModelPair
    enable_hyde: bool = True
    enable_rerank: bool = True

    @property
    def embedding_model(self) -> str:
        return self.pair.embedding_model

    @property
    def embedding_provider(self) -> str:
        return self.pair.embedding_provider

    @property
    def embedding_dimension(self) -> int:
        return self.pair.embedding_dimension

    @property
    def hyde_model(self) -> str:
        return self.pair.hyde_model

    @property
    def rerank_model(self) -> str:
        return self.pair.rerank_model

    @classmethod
    async def resolve(
        cls,
        pg: PostgresClient | None = None,
    ) -> RetrievalConfig:
        """Resolve the config from the active pair.

        Boot-blocking: if the live ``llm_providers`` rows don't match an
        active pair, this raises :class:`IncompatiblePairError`. The
        caller decides what to do (the typical response is to fail
        startup with a clear error).

        2026-07-22 centralization: before validating, sync the active
        pair from the live ``llm_providers.is_default`` rows if the
        pair has ``auto_sync=true`` (the default). This makes the pair
        a derived projection — operators can flip a default at the DB
        level and the next ``resolve()`` self-heals. Operators can
        lock a pair by setting ``auto_sync=false``.
        """
        client = pg if pg is not None else PostgresClient()
        try:
            # Auto-sync the active pair from the live defaults. This is
            # idempotent and a no-op if the pair is already aligned (or
            # if auto_sync=false on the existing row).
            active_rows = await client.model_pair_list_active()
            if active_rows:
                active_name = active_rows[0].get("name") or "auto"
                await sync_active_pair_from_defaults(client, name=active_name)
            else:
                # No active pair yet — create one from current defaults
                # so a fresh deployment boots without manual seeding.
                try:
                    await sync_active_pair_from_defaults(client, name="auto")
                except RuntimeError as exc:
                    # No providers seeded yet — defer to the validator
                    # which raises a clearer error.
                    if pg is None:
                        await client.close()
                    raise IncompatiblePairError(f"cannot auto-derive a model_pair from defaults: {exc}") from exc
            reg = PairRegistry(pg=client)
            pair = await reg.validate_active_pair()  # raises IncompatiblePairError
        finally:
            if pg is None:
                await client.close()
        return cls(
            pair=pair,
            enable_hyde=_env_bool("RETRIEVAL_ENABLE_HYDE", True),
            enable_rerank=_env_bool("RETRIEVAL_ENABLE_RERANK", True),
        )
