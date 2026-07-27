"""Regression test: taxonomic/membership relationships must reject self-loops.

Live bug (2026-07-22 Fallout ingest): a name-resolution collision produced a
"Railroad Agent SUBTYPE_OF Railroad Agent" self-loop edge. The tool-layer
guard previously only blocked self-loops for KNOWS/ALLIED_WITH/HOSTILE_TO.
"""

from uuid import uuid4

import pytest

from monitor_data.schemas.relationships import RelationshipCreate, RelationshipType


@pytest.mark.parametrize(
    "rel_type",
    [
        RelationshipType.SUBTYPE_OF,
        RelationshipType.DERIVES_FROM,
        RelationshipType.INSTANCE_OF,
        RelationshipType.PART_OF,
        RelationshipType.MEMBER_OF,
        RelationshipType.SUBGROUP_OF,
    ],
)
def test_self_loop_rejected_for_taxonomic_and_membership_types(monkeypatch, rel_type):
    from monitor_data.tools.neo4j_tools import relationships as rel_module

    same_id = uuid4()
    monkeypatch.setattr(rel_module, "get_neo4j_client", lambda: None)
    monkeypatch.setattr(rel_module, "verify_node_exists", lambda *_a, **_k: None)

    params = RelationshipCreate(
        from_entity_id=same_id,
        to_entity_id=same_id,
        rel_type=rel_type,
        category="taxonomic",
    )

    with pytest.raises(ValueError, match="Self-referencing"):
        rel_module.neo4j_create_relationship(params)
