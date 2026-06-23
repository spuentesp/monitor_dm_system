"""
Tests for the data topology module.

Verifies structural correctness of MONITOR_TOPOLOGY and the gap_report() helper.
All tests are pure-unit — no DB connections required.
"""

from monitor_data.schemas.rpg_ontology.meta import DataEdgeSpec, StorageBackend
from monitor_data.schemas.rpg_ontology.topology import (
    CollectionSpec,
    DataTopology,
    IndexedBy,
    MONITOR_TOPOLOGY,
    StorageNode,
    gap_report,
)


# ===========================================================================
# CollectionSpec
# ===========================================================================


class TestCollectionSpec:
    def test_defaults(self):
        c = CollectionSpec(name="test_col", description="A test collection")
        assert c.indexed_by == IndexedBy.NO_INDEX
        assert c.index_fields == []
        assert c.key_fields == []
        assert c.schema_module is None
        assert c.notes is None
        assert c.has_mcp_tools is True

    def test_all_fields(self):
        c = CollectionSpec(
            name="things",
            description="All the things",
            schema_module="monitor_data.schemas.things",
            indexed_by=IndexedBy.FORMAL_INDEX,
            index_fields=["world_id", "created_at"],
            key_fields=["id"],
            notes="Some note",
            has_mcp_tools=False,
        )
        assert c.indexed_by == IndexedBy.FORMAL_INDEX
        assert "world_id" in c.index_fields
        assert c.has_mcp_tools is False

    def test_vector_indexed_by(self):
        c = CollectionSpec(
            name="embeddings",
            description="Vector collection",
            indexed_by=IndexedBy.VECTOR,
        )
        assert c.indexed_by == IndexedBy.VECTOR

    def test_primary_key_indexed_by(self):
        c = CollectionSpec(
            name="kv",
            description="KV store",
            indexed_by=IndexedBy.PRIMARY_KEY,
            key_fields=["key"],
        )
        assert c.key_fields == ["key"]


# ===========================================================================
# StorageNode
# ===========================================================================


class TestStorageNode:
    def test_active_node(self):
        node = StorageNode(
            backend=StorageBackend.MONGODB,
            technology="MongoDB 7.0",
            description="Test node",
            docker_service="mongodb",
            default_port=27017,
            is_active=True,
        )
        assert node.is_active is True
        assert node.is_deployed is True
        assert node.collections == []

    def test_inactive_deployed_node(self):
        node = StorageNode(
            backend=StorageBackend.OPENSEARCH,
            technology="OpenSearch 2.11",
            description="Unused backend",
            docker_service="opensearch",
            default_port=9200,
            is_deployed=True,
            is_active=False,
        )
        assert node.is_deployed is True
        assert node.is_active is False

    def test_node_with_collections(self):
        node = StorageNode(
            backend=StorageBackend.QDRANT,
            technology="Qdrant 1.7",
            description="Vectors",
            docker_service="qdrant",
            default_port=6333,
            is_active=True,
            collections=[
                CollectionSpec(
                    name="scenes",
                    description="Scene vectors",
                    indexed_by=IndexedBy.VECTOR,
                ),
                CollectionSpec(
                    name="memories",
                    description="Memory vectors",
                    indexed_by=IndexedBy.VECTOR,
                ),
            ],
        )
        assert len(node.collections) == 2
        assert node.collections[0].name == "scenes"


# ===========================================================================
# DataTopology
# ===========================================================================


class TestDataTopology:
    def _make_node(self, backend: StorageBackend, is_active: bool = True) -> StorageNode:
        return StorageNode(
            backend=backend,
            technology="Test",
            description="Test node",
            docker_service="test",
            default_port=1234,
            is_active=is_active,
        )

    def _make_edge(
        self,
        edge_id: str,
        from_backend: StorageBackend,
        to_backend: StorageBackend,
    ) -> DataEdgeSpec:
        return DataEdgeSpec(
            edge_id=edge_id,
            description="Test edge",
            from_backend=from_backend,
            from_collection="col_a",
            from_field="field_a",
            to_backend=to_backend,
            to_collection="col_b",
            to_field="field_b",
        )

    def test_get_node_found(self):
        topo = DataTopology(
            storage_nodes=[
                self._make_node(StorageBackend.NEO4J),
                self._make_node(StorageBackend.MONGODB),
            ]
        )
        node = topo.get_node(StorageBackend.NEO4J)
        assert node is not None
        assert node.backend == StorageBackend.NEO4J

    def test_get_node_not_found(self):
        topo = DataTopology(storage_nodes=[self._make_node(StorageBackend.NEO4J)])
        assert topo.get_node(StorageBackend.OPENSEARCH) is None

    def test_edges_from(self):
        topo = DataTopology(
            storage_nodes=[
                self._make_node(StorageBackend.MONGODB),
                self._make_node(StorageBackend.NEO4J),
                self._make_node(StorageBackend.QDRANT),
            ],
            data_edges=[
                self._make_edge("e1", StorageBackend.MONGODB, StorageBackend.NEO4J),
                self._make_edge("e2", StorageBackend.MONGODB, StorageBackend.QDRANT),
                self._make_edge("e3", StorageBackend.NEO4J, StorageBackend.QDRANT),
            ],
        )
        mongo_edges = topo.edges_from(StorageBackend.MONGODB)
        assert len(mongo_edges) == 2
        assert all(e.from_backend == StorageBackend.MONGODB for e in mongo_edges)

    def test_edges_to(self):
        topo = DataTopology(
            storage_nodes=[
                self._make_node(StorageBackend.MONGODB),
                self._make_node(StorageBackend.NEO4J),
                self._make_node(StorageBackend.QDRANT),
            ],
            data_edges=[
                self._make_edge("e1", StorageBackend.MONGODB, StorageBackend.QDRANT),
                self._make_edge("e2", StorageBackend.NEO4J, StorageBackend.QDRANT),
                self._make_edge("e3", StorageBackend.MONGODB, StorageBackend.NEO4J),
            ],
        )
        qdrant_edges = topo.edges_to(StorageBackend.QDRANT)
        assert len(qdrant_edges) == 2
        assert all(e.to_backend == StorageBackend.QDRANT for e in qdrant_edges)

    def test_edges_from_empty(self):
        topo = DataTopology(
            storage_nodes=[self._make_node(StorageBackend.POSTGRES)],
            data_edges=[],
        )
        assert topo.edges_from(StorageBackend.POSTGRES) == []

    def test_empty_topology(self):
        topo = DataTopology(storage_nodes=[])
        assert topo.storage_nodes == []
        assert topo.data_edges == []


# ===========================================================================
# MONITOR_TOPOLOGY — structural completeness
# ===========================================================================


class TestMonitorTopology:
    def test_all_six_backends_present(self):
        backends = {n.backend for n in MONITOR_TOPOLOGY.storage_nodes}
        assert backends == {
            StorageBackend.NEO4J,
            StorageBackend.MONGODB,
            StorageBackend.QDRANT,
            StorageBackend.MINIO,
            StorageBackend.POSTGRES,
            StorageBackend.OPENSEARCH,
        }

    def test_exactly_six_nodes(self):
        assert len(MONITOR_TOPOLOGY.storage_nodes) == 6

    def test_opensearch_is_inactive(self):
        node = MONITOR_TOPOLOGY.get_node(StorageBackend.OPENSEARCH)
        assert node is not None
        assert node.is_deployed is True
        assert node.is_active is False

    def test_neo4j_is_active(self):
        node = MONITOR_TOPOLOGY.get_node(StorageBackend.NEO4J)
        assert node is not None
        assert node.is_active is True

    def test_mongodb_has_18_collections(self):
        node = MONITOR_TOPOLOGY.get_node(StorageBackend.MONGODB)
        assert node is not None
        assert len(node.collections) == 18

    def test_neo4j_has_11_collections(self):
        node = MONITOR_TOPOLOGY.get_node(StorageBackend.NEO4J)
        assert node is not None
        assert len(node.collections) == 11

    def test_qdrant_has_5_collections(self):
        node = MONITOR_TOPOLOGY.get_node(StorageBackend.QDRANT)
        assert node is not None
        assert len(node.collections) == 5

    def test_postgres_has_13_collections(self):
        node = MONITOR_TOPOLOGY.get_node(StorageBackend.POSTGRES)
        assert node is not None
        assert len(node.collections) == 13

    def test_opensearch_has_no_collections(self):
        node = MONITOR_TOPOLOGY.get_node(StorageBackend.OPENSEARCH)
        assert node is not None
        assert len(node.collections) == 0

    def test_at_least_one_edge(self):
        assert len(MONITOR_TOPOLOGY.data_edges) > 0

    def test_all_edge_ids_unique(self):
        ids = [e.edge_id for e in MONITOR_TOPOLOGY.data_edges]
        assert len(ids) == len(set(ids)), "Duplicate edge_ids found"

    def test_mongodb_has_outbound_edges(self):
        edges = MONITOR_TOPOLOGY.edges_from(StorageBackend.MONGODB)
        assert len(edges) > 0

    def test_neo4j_receives_edges(self):
        edges = MONITOR_TOPOLOGY.edges_to(StorageBackend.NEO4J)
        assert len(edges) > 0

    def test_qdrant_receives_edges(self):
        edges = MONITOR_TOPOLOGY.edges_to(StorageBackend.QDRANT)
        assert len(edges) > 0

    def test_minio_receives_edges(self):
        edges = MONITOR_TOPOLOGY.edges_to(StorageBackend.MINIO)
        assert len(edges) > 0

    def test_character_working_state_collection_exists(self):
        node = MONITOR_TOPOLOGY.get_node(StorageBackend.MONGODB)
        names = [c.name for c in node.collections]
        assert "character_working_state" in names

    def test_character_sheet_index_exists_in_postgres(self):
        node = MONITOR_TOPOLOGY.get_node(StorageBackend.POSTGRES)
        names = [c.name for c in node.collections]
        assert "character_sheet_index" in names

    def test_game_system_schemas_has_spec_noted(self):
        node = MONITOR_TOPOLOGY.get_node(StorageBackend.POSTGRES)
        coll = next(c for c in node.collections if c.name == "game_system_schemas")
        assert "spec" in coll.description.lower() or (coll.notes and "spec" in coll.notes.lower())

    def test_working_state_to_character_sheet_edge_exists(self):
        """The ephemeral working_state → canonical PG sheet edge must be documented."""
        edge = next(
            (
                e
                for e in MONITOR_TOPOLOGY.data_edges
                if e.edge_id == "working_state_to_character_sheet"
            ),
            None,
        )
        assert edge is not None
        assert edge.from_backend == StorageBackend.MONGODB
        assert edge.to_backend == StorageBackend.POSTGRES

    def test_worlds_to_neo4j_edge_exists(self):
        edge = next(
            (e for e in MONITOR_TOPOLOGY.data_edges if e.edge_id == "worlds_to_neo4j_universe"),
            None,
        )
        assert edge is not None
        assert edge.from_backend == StorageBackend.POSTGRES
        assert edge.to_backend == StorageBackend.NEO4J

    def test_minio_edge_is_unenforced(self):
        edges_to_minio = MONITOR_TOPOLOGY.edges_to(StorageBackend.MINIO)
        # All MinIO edges are soft references (S3 has no FK support)
        assert all(not e.is_enforced for e in edges_to_minio)

    def test_only_pg_internal_edge_is_enforced(self):
        """The one enforced edge is the PostgreSQL FK from character_sheet → worlds."""
        enforced = [e for e in MONITOR_TOPOLOGY.data_edges if e.is_enforced]
        assert len(enforced) >= 1
        edge = next(e for e in enforced if e.edge_id == "character_sheet_to_world")
        assert edge.from_backend == StorageBackend.POSTGRES
        assert edge.to_backend == StorageBackend.POSTGRES

    def test_all_collections_have_name_and_description(self):
        for node in MONITOR_TOPOLOGY.storage_nodes:
            for coll in node.collections:
                assert coll.name, f"Missing name in {node.backend}"
                assert coll.description, f"Missing description for {coll.name} in {node.backend}"


# ===========================================================================
# gap_report()
# ===========================================================================


class TestGapReport:
    def test_opensearch_gap_reported(self):
        gaps = gap_report(MONITOR_TOPOLOGY)
        opensearch_gaps = [g for g in gaps if "opensearch" in g.lower()]
        assert len(opensearch_gaps) > 0

    def test_backend_inactive_tag_present(self):
        gaps = gap_report(MONITOR_TOPOLOGY)
        assert any("[BACKEND_INACTIVE]" in g for g in gaps)

    def test_no_mcp_tools_tag_present(self):
        gaps = gap_report(MONITOR_TOPOLOGY)
        assert any("[NO_MCP_TOOLS]" in g for g in gaps)

    def test_referential_integrity_tag_present(self):
        gaps = gap_report(MONITOR_TOPOLOGY)
        assert any("[REFERENTIAL_INTEGRITY]" in g for g in gaps)

    def test_collection_gap_tag_present(self):
        gaps = gap_report(MONITOR_TOPOLOGY)
        assert any("[COLLECTION_GAP]" in g for g in gaps)

    def test_working_state_gap_reported(self):
        gaps = gap_report(MONITOR_TOPOLOGY)
        # character_working_state has 'GAP' in its notes
        working_state_gaps = [g for g in gaps if "character_working_state" in g]
        assert len(working_state_gaps) > 0

    def test_gap_report_returns_list(self):
        result = gap_report(MONITOR_TOPOLOGY)
        assert isinstance(result, list)
        assert all(isinstance(g, str) for g in result)

    def test_gap_report_empty_topology(self):
        """An empty topology should still return the referential integrity note
        (because 0 unenforced edges means the note is skipped)."""
        topo = DataTopology(storage_nodes=[])
        gaps = gap_report(topo)
        # No nodes → no inactive backend gaps, no collection gaps
        inactive = [g for g in gaps if "[BACKEND_INACTIVE]" in g]
        assert len(inactive) == 0

    def test_fully_active_topology_has_no_inactive_backend_gap(self):
        """A topology where all nodes are active should have no BACKEND_INACTIVE gap."""
        topo = DataTopology(
            storage_nodes=[
                StorageNode(
                    backend=StorageBackend.NEO4J,
                    technology="Neo4j",
                    description="active",
                    docker_service="neo4j",
                    default_port=7687,
                    is_active=True,
                    is_deployed=True,
                )
            ]
        )
        gaps = gap_report(topo)
        assert not any("[BACKEND_INACTIVE]" in g for g in gaps)

    def test_inactive_node_always_flagged(self):
        topo = DataTopology(
            storage_nodes=[
                StorageNode(
                    backend=StorageBackend.OPENSEARCH,
                    technology="OpenSearch",
                    description="unused",
                    docker_service="opensearch",
                    default_port=9200,
                    is_deployed=True,
                    is_active=False,
                )
            ]
        )
        gaps = gap_report(topo)
        assert any("[BACKEND_INACTIVE]" in g for g in gaps)

    def test_collection_without_mcp_tools_flagged(self):
        topo = DataTopology(
            storage_nodes=[
                StorageNode(
                    backend=StorageBackend.MONGODB,
                    technology="MongoDB",
                    description="Mongo",
                    docker_service="mongodb",
                    default_port=27017,
                    is_active=True,
                    collections=[
                        CollectionSpec(
                            name="orphan_col",
                            description="No tools for this one",
                            has_mcp_tools=False,
                        )
                    ],
                )
            ]
        )
        gaps = gap_report(topo)
        assert any("[NO_MCP_TOOLS]" in g and "orphan_col" in g for g in gaps)
