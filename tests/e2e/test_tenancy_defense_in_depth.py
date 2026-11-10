"""Integration: defense-in-depth owner assertions and usage quotas (Phase 6 gaps).

Runs against the real local stack (Postgres ownership registry + MongoDB),
so it needs ``RUN_INTEGRATION=1`` and the compose databases up:

    RUN_INTEGRATION=1 uv run pytest tests/e2e/test_tenancy_defense_in_depth.py -v

Covers the two seams that only exist end-to-end:

- A write tool called with a foreign owner bound in context is refused at
  the tool boundary (the HTTP guard being missed or bypassed cannot leak a
  cross-tenant write), while the matching owner and the no-owner local mode
  keep working.
- The per-model-call usage accounting drives the daily cap: one user at the
  cap gets the typed refusal on the next model call, the other user is
  unaffected.

Rows created here carry random ids and are removed again where the client
exposes deletes; the usage rows are idempotent per user/day.
"""

from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

import pytest

pytestmark = pytest.mark.integration


def _create_user(pg, uid: UUID, email: str) -> None:  # type: ignore[no-untyped-def]
    asyncio.run(
        pg.user_create(
            {
                "id": uid,
                "email": email,
                "email_normalized": email,
                "username": f"tenancy-{uid.hex[:8]}",
                "username_normalized": f"tenancy-{uid.hex[:8]}",
                "password_hash": "x",
            }
        )
    )


@pytest.mark.integration
class TestOwnerAssertionIntegration:
    def test_foreign_owner_write_refused_matching_and_none_pass(self) -> None:
        from monitor_data.db.mongodb import get_mongodb_client
        from monitor_data.db.postgres import get_postgres_client
        from monitor_data.schemas.memories import MemoryCreate
        from monitor_data.tenancy import OwnerViolationError, set_owner_id
        from monitor_data.tools.mongodb_tools.memories import mongodb_create_memory, mongodb_delete_memory

        pg = get_postgres_client()
        mongo = get_mongodb_client()

        owner_a, owner_b = uuid4(), uuid4()
        universe_a, universe_b = str(uuid4()), str(uuid4())
        _create_user(pg, owner_a, f"a-{owner_a.hex[:8]}@tenancy.test")
        _create_user(pg, owner_b, f"b-{owner_b.hex[:8]}@tenancy.test")
        for world_id, owner in ((universe_a, owner_a), (universe_b, owner_b)):
            asyncio.run(pg.world_upsert({"id": world_id, "owner_id": owner, "label": "tenancy-int", "active": True}))

        entity_id = uuid4()
        characters = mongo.get_collection("characters")
        characters.insert_one({"id": str(entity_id), "versions": [], "name": "tenancy-int"})
        created_id: UUID | None = None
        unbound_id: UUID | None = None
        try:
            # Foreign owner in context: refused, nothing written.
            set_owner_id(owner_a)
            with pytest.raises(OwnerViolationError):
                mongodb_create_memory(
                    MemoryCreate(universe_id=uuid4(), entity_id=entity_id, text="foreign write")
                )
            assert not mongo.get_collection("character_memories").find_one({"text": "foreign write"})

            # Matching owner: the write completes.
            created = mongodb_create_memory(
                MemoryCreate(universe_id=universe_a, entity_id=entity_id, text="owned write")
            )
            created_id = created.memory_id
            assert created.text == "owned write"

            # No owner in context (local mode / scripts / workers): unchanged.
            set_owner_id(None)
            unbound = mongodb_create_memory(
                MemoryCreate(universe_id=universe_b, entity_id=entity_id, text="unbound write")
            )
            unbound_id = unbound.memory_id
            assert unbound.text == "unbound write"
        finally:
            set_owner_id(None)
            for mem_id in (created_id, unbound_id):
                if mem_id is not None:
                    try:
                        mongodb_delete_memory(mem_id)
                    except Exception:  # noqa: BLE001, S110  # reason: best-effort cleanup in an integration test
                        pass
            characters.delete_one({"id": str(entity_id)})


@pytest.mark.integration
class TestUsageQuotaIntegration:
    def test_capped_user_refused_on_next_model_call_other_unaffected(self) -> None:
        from monitor_data.db.postgres import get_postgres_client
        from monitor_data.tenancy import set_owner_id
        from monitor_data.usage import QuotaExceededError, enforce_owner_quota, record_model_usage

        pg = get_postgres_client()
        capped, fresh = uuid4(), uuid4()
        _create_user(pg, capped, f"capped-{capped.hex[:8]}@tenancy.test")
        _create_user(pg, fresh, f"fresh-{fresh.hex[:8]}@tenancy.test")
        asyncio.run(pg.usage_limit_set(capped, daily_token_cap=None, daily_call_cap=1, exempt=False))
        asyncio.run(pg.usage_record(capped, tokens=0, calls=1))

        try:
            set_owner_id(capped)
            with pytest.raises(QuotaExceededError):
                enforce_owner_quota()
            set_owner_id(fresh)
            enforce_owner_quota()  # the other user is unaffected
            record_model_usage(tokens=5, calls=1)
            usage = asyncio.run(pg.usage_get(fresh))
            assert int(usage["calls"]) >= 1
        finally:
            set_owner_id(None)
            asyncio.run(pg.usage_limit_set(capped, daily_token_cap=None, daily_call_cap=None, exempt=False))
