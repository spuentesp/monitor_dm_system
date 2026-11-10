"""Tests for the universe fork endpoint's multi-world wiring (Phase 4):
bindings registration + Mongo/Qdrant/MinIO data cloning. Hermetic — all
external clients are mocked."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from monitor_ui.auth import Principal
from monitor_ui.routers import universes

_LOCAL = Principal(user_id=uuid4(), is_admin=True, via="local")

pytestmark = pytest.mark.usefixtures("local_auth_mode")


SRC = str(uuid4())
DST = str(uuid4())


def test_default_world_bindings_derivation():
    b = universes._default_world_bindings(SRC)
    short = SRC.replace("-", "")[:12]
    assert b["world_id"] == SRC
    assert b["neo4j_database"] == "neo4j"  # Community: single user DB, Universe-node scoping
    assert b["mongodb_collection_prefix"] == f"w{short}_"
    assert b["qdrant_collection"] == f"world_{short}"
    assert b["minio_prefix"] == f"{short}/"


@pytest.mark.asyncio
async def test_fork_registers_bindings_and_clones_data():
    db = MagicMock()
    db.world_bindings_get = AsyncMock(return_value={"qdrant_collection": "world_src", "minio_prefix": "srcp/"})
    db.world_upsert = AsyncMock()
    db.world_bindings_upsert = AsyncMock()

    universe = MagicMock(multiverse_id=uuid4(), name="Base")

    minio = MagicMock()
    minio.copy_prefix = AsyncMock(return_value={"copied": 3})

    with (
        patch.object(universes, "neo4j_get_universe", return_value=universe),
        patch(
            "monitor_data.tools.neo4j_tools.neo4j_fork_universe",
            return_value={"new_universe_id": DST, "entities_cloned": 5, "relationships_cloned": 7},
        ),
        patch.object(universes, "mongodb_fork_universe_data", return_value={"total_copied": 9}) as mongo_fork,
        patch.object(universes, "qdrant_clone_collection", return_value={"points_copied": 11}) as qdrant_clone,
        patch.object(universes, "get_minio_client", return_value=minio),
    ):
        result = await universes.fork_universe(SRC, universes.ForkRequest(name="My Story"), principal=_LOCAL, db=db)

    assert result["status"] == "forked"
    assert result["new_universe_id"] == DST
    assert result["entities_cloned"] == 5

    # bindings registered for the fork with derived prefixes
    db.world_bindings_upsert.assert_awaited_once()
    bindings = db.world_bindings_upsert.await_args.args[0]
    assert bindings["world_id"] == DST
    assert bindings["mongodb_collection_prefix"].startswith("w")

    # data cloned from source bindings to destination bindings
    mongo_fork.assert_called_once_with(SRC, DST, bindings["mongodb_collection_prefix"])
    qdrant_clone.assert_called_once_with("world_src", bindings["qdrant_collection"])
    minio.copy_prefix.assert_awaited_once_with("srcp/", bindings["minio_prefix"])
    assert result["mongo"] == {"total_copied": 9}
    assert result["qdrant"] == {"points_copied": 11}
    assert result["minio"] == {"copied": 3}


@pytest.mark.asyncio
async def test_create_universe_registers_default_bindings():
    """create_universe must write world_db_bindings alongside the worlds row."""
    db = MagicMock()
    db.world_upsert = AsyncMock()
    db.world_bindings_upsert = AsyncMock()
    new_u = MagicMock(id=UUID(DST), multiverse_id=uuid4(), name="W")
    new_u.id = UUID(DST)

    # UniverseResponse-like object needs to work with _u_to_dict; patch it.
    with (
        patch.object(universes, "neo4j_create_universe", return_value=new_u),
        patch.object(universes, "_u_to_dict", return_value={"id": DST}),
    ):
        out = await universes.create_universe(
            universes.UniverseCreate(name="W", multiverse_id=str(uuid4()), description="d"),
            principal=_LOCAL,
            db=db,
        )

    assert out == {"id": DST}
    db.world_upsert.assert_awaited_once()
    db.world_bindings_upsert.assert_awaited_once()
    bindings = db.world_bindings_upsert.await_args.args[0]
    assert bindings["world_id"] == DST
