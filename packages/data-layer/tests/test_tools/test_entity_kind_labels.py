"""Entities carry their kind as a label, which many queries match on.

Parties, agendas, story lookups and the memory entity check all match
`:EntityInstance` / `:EntityArchetype`, so an entity without one is invisible
to them.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any
from unittest.mock import Mock, patch
from uuid import UUID, uuid4

import pytest

from monitor_data.schemas.base import EntityType
from monitor_data.schemas.entities import EntityCreate
from monitor_data.tools.neo4j_tools import neo4j_create_entity
from monitor_data.tools.neo4j_tools.core import _clone_entity_into_universe

SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "migrate_entity_kind_labels.py"


@pytest.mark.parametrize(("is_archetype", "label"), [(True, ":EntityArchetype"), (False, ":EntityInstance")])
@patch("monitor_data.tools.neo4j_tools.entities.get_neo4j_client")
def test_create_labels_the_entity_kind(
    get_client: Mock, mock_neo4j_client: Mock, is_archetype: bool, label: str
) -> None:
    universe = str(uuid4())
    get_client.return_value = mock_neo4j_client
    mock_neo4j_client.execute_read.return_value = [{"id": universe}]
    mock_neo4j_client.execute_write.return_value = [
        {
            "e": {
                "id": str(uuid4()),
                "universe_id": universe,
                "name": "Rook",
                "entity_type": "character",
                "is_archetype": is_archetype,
                "description": "",
                "properties": "{}",
                "state_tags": [],
                "canon_level": "canon",
                "confidence": 1.0,
                "authority": "system",
                "created_at": "2026-01-01T00:00:00+00:00",
            }
        }
    ]

    neo4j_create_entity(
        EntityCreate(
            universe_id=UUID(universe), name="Rook", entity_type=EntityType.CHARACTER, is_archetype=is_archetype
        )
    )

    query = mock_neo4j_client.execute_write.call_args.args[0]
    assert f"CREATE (e:Entity{label}" in query


@pytest.mark.parametrize(("is_archetype", "label"), [(True, "EntityArchetype"), (False, "EntityInstance")])
def test_clone_keeps_the_entity_kind(is_archetype: bool, label: str) -> None:
    client = Mock()
    _clone_entity_into_universe(client, str(uuid4()), {"id": "old", "is_archetype": is_archetype}, "now")
    query = client.execute_write.call_args.args[0]
    assert f"CREATE (e:Entity:{label})" in query


def _migration() -> Any:
    spec = importlib.util.spec_from_file_location("migrate_entity_kind_labels", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_migration_labels_only_entities_missing_their_kind() -> None:
    client = Mock()
    client.execute_read.return_value = [{"archetypes": 2, "instances": 5}]
    client.execute_write.return_value = [{"labelled": 0}]

    counts = _migration().migrate(client, dry_run=False)

    queries = [c.args[0] for c in client.execute_write.call_args_list]
    assert len(queries) == 2
    assert any(
        "SET e:EntityArchetype" in q and "NOT e:EntityArchetype" in q and "is_archetype = true" in q for q in queries
    )
    assert any("SET e:EntityInstance" in q and "NOT e:EntityInstance" in q for q in queries)
    assert all("EntityTemplate" in q for q in queries)  # templates are neither kind
    assert counts == {"archetypes": 2, "instances": 5}


def test_migration_dry_run_writes_nothing() -> None:
    client = Mock()
    client.execute_read.return_value = [{"archetypes": 1, "instances": 3}]

    assert _migration().migrate(client, dry_run=True) == {"archetypes": 1, "instances": 3}
    client.execute_write.assert_not_called()
