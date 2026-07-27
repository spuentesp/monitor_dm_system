"""
LLM-provider seeding helpers for ``monitor init`` and the standalone seed scripts.

LAYER: 2 (agents)
IMPORTS FROM: monitor_data (Layer 1) — PostgresClient only.
NEVER IMPORTS: monitor_cli (Layer 3).

This module exposes a single async function ``seed_provider(...)`` plus a
few small helpers (``list_providers``, ``unset_role_default``). Every existing
``scripts/seed_*_provider.py`` script is being migrated to call this helper
so that behaviour stays in one place — wizard + standalone script end up
updating the same ``llm_providers`` rows through the same code path.

Reuse: every write goes through ``PostgresClient.provider_upsert`` (defined
at packages/data-layer/src/monitor_data/db/postgres.py:530). No new SQL is
introduced here beyond the role-scoped "unset prior default" update needed
because the data-layer only exposes a global ``provider_set_default`` that
clears defaults across all roles.
"""

from __future__ import annotations

import logging
from typing import Any

from monitor_data.db.postgres import PostgresClient

logger = logging.getLogger(__name__)

__all__ = [
    "get_role_default",
    "list_providers",
    "seed_provider",
    "unset_role_default",
]


async def list_providers() -> list[dict[str, Any]]:
    """Return all llm_providers rows (most-recently-created-first)."""
    pg = PostgresClient()
    try:
        return await pg.providers_list()
    finally:
        await pg.close()


async def unset_role_default(role: str, *, except_id: str | None = None) -> int:
    """Unset ``is_default`` on every row in the given role (optionally except one id).

    Returns the number of rows that were cleared. Used by ``seed_provider``
    before promoting a new row to default, so two providers never both
    claim the same role.
    """
    pg = PostgresClient()
    try:
        return await pg.unset_role_default(role, except_id=except_id)
    finally:
        await pg.close()


async def get_role_default(role: str) -> dict[str, Any] | None:
    """Return the current default provider row for ``role``, or None."""
    pg = PostgresClient()
    try:
        return await pg.get_role_default(role)
    finally:
        await pg.close()


async def seed_provider(
    *,
    id: str,
    name: str,
    provider_type: str,
    model: str,
    role: str,
    api_key: str | None = None,
    base_url: str | None = None,
    is_default: bool = False,
    status: str = "connected",
    model_params: dict[str, Any] | None = None,
    latency_ms: int | None = None,
) -> None:
    """
    Idempotently upsert a single LLM provider into ``llm_providers``.

    If ``is_default=True``, this first unsets ``is_default`` on every other
    row that has the same ``role`` so two providers never claim the role.

    Args:
        id: Stable identifier for the row (e.g. ``"anthropic-default"``).
        name: Human-readable label shown in ``monitor doctor``.
        provider_type: Provider enum string (e.g. ``"anthropic"``, ``"ollama"``,
            ``"github_models"``). Must match what ``LLMProviderType`` expects.
        model: Model name (e.g. ``"claude-sonnet-4-20250514"``).
        role: One of ``"light"``, ``"standard"``, ``"heavy"``, ``"embedding"``.
        api_key: Optional API key. Empty string is stored as ``""`` (env fallback
            is still consulted by ``LLMRegistry._resolve_api_key``).
        base_url: Optional override; falls back to provider-specific defaults.
        is_default: Promote this row to the role default. Atomic with the upsert.
        status: ``"connected"`` (default) or ``"error"`` for the ingest-doctor view.
        model_params: Serialized to JSON and stored in ``model_params`` column.
        latency_ms: Optional last-known latency for ``monitor doctor`` display.

    Examples:
        >>> await seed_provider(
        ...     id="anthropic-default",
        ...     name="Anthropic Claude",
        ...     provider_type="anthropic",
        ...     model="claude-sonnet-4-20250514",
        ...     role="heavy",
        ...     api_key="sk-ant-...",
        ...     is_default=True,
        ... )
    """
    if role not in ("light", "standard", "heavy", "embedding"):
        raise ValueError(f"invalid role: {role!r}")

    pg = PostgresClient()
    try:
        if is_default:
            # Atomic: clear other role defaults first so we don't end up with
            # two rows both claiming is_default=true for the same role.
            await pg.unset_role_default(role, except_id=id)

        payload = {
            "id": id,
            "name": name,
            "provider": provider_type,
            "model": model,
            "api_key": api_key or "",
            "base_url": base_url,
            "model_params": model_params or {"temperature": 0.7, "max_tokens": 4096},
            "role": role,
            "status": status,
            "latency_ms": latency_ms,
            "is_default": is_default,
        }
        await pg.provider_upsert(payload)
        logger.info("seeded provider %s [%s] default=%s", id, role, is_default)
    finally:
        await pg.close()
