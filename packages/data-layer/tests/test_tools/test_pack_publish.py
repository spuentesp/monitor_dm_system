"""Tests for the pack publish gate + public gallery and the universe graph
gate (Phase 5). Hermetic — Mongo/Neo4j/completeness are mocked."""

from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from monitor_data.schemas.knowledge_packs import KnowledgePackStatus
from monitor_data.tools.mongodb_tools import knowledge_packs as kp
from monitor_data.tools.neo4j_tools import graph_algos


def _pack(status: KnowledgePackStatus, name: str = "Base World"):
    pack = MagicMock()
    pack.pack_id = uuid4()
    pack.name = name
    pack.status = status
    return pack


def _mock_mongo(extraction: dict | None = None):
    client = MagicMock()
    coll = MagicMock()
    coll.find_one.return_value = {"pack_id": "x", "extraction": extraction}
    client.get_collection.return_value = coll
    return client, coll


@pytest.mark.unit
def test_published_status_exists():
    assert KnowledgePackStatus.PUBLISHED.value == "published"


@pytest.mark.unit
def test_quality_report_publishable_when_ready_and_complete():
    pack = _pack(KnowledgePackStatus.READY)
    client, _ = _mock_mongo({"active_backend": "gliner"})
    completeness = MagicMock(overall_score=0.9, overall_status="complete")
    completeness.categories.model_dump.return_value = {}
    completeness.recommendations = []

    with (
        patch.object(kp, "mongodb_get_knowledge_pack", return_value=pack),
        patch.object(kp, "get_mongodb_client", return_value=client),
        patch("monitor_data.tools.pack_completeness.compute_knowledge_pack_completeness", return_value=completeness),
    ):
        report = kp.mongodb_pack_quality_report(pack.pack_id)

    assert report["publishable"] is True
    assert report["reasons"] == []
    assert report["overall_score"] == 0.9
    assert report["extraction"] == {"active_backend": "gliner"}


@pytest.mark.unit
def test_quality_report_rejects_pending_and_low_score():
    pack = _pack(KnowledgePackStatus.PENDING)
    client, _ = _mock_mongo()
    completeness = MagicMock(overall_score=0.1, overall_status="minimal")
    completeness.categories.model_dump.return_value = {}
    completeness.recommendations = ["add entities"]

    with (
        patch.object(kp, "mongodb_get_knowledge_pack", return_value=pack),
        patch.object(kp, "get_mongodb_client", return_value=client),
        patch("monitor_data.tools.pack_completeness.compute_knowledge_pack_completeness", return_value=completeness),
    ):
        report = kp.mongodb_pack_quality_report(pack.pack_id, min_score=0.5)

    assert report["publishable"] is False
    assert len(report["reasons"]) == 2  # pending status + low score


@pytest.mark.unit
def test_publish_sets_status_and_stamps():
    pack = _pack(KnowledgePackStatus.READY)
    client, coll = _mock_mongo()
    completeness = MagicMock(overall_score=0.9, overall_status="complete")
    completeness.categories.model_dump.return_value = {}
    completeness.recommendations = []
    coll.find_one.return_value = {"pack_id": str(pack.pack_id), "status": "published"}

    with (
        patch.object(kp, "mongodb_get_knowledge_pack", return_value=pack),
        patch.object(kp, "get_mongodb_client", return_value=client),
        patch("monitor_data.tools.pack_completeness.compute_knowledge_pack_completeness", return_value=completeness),
        patch.object(kp, "_convert_knowledge_pack_doc", return_value={"pack_id": str(pack.pack_id)}),
    ):
        result = kp.mongodb_publish_knowledge_pack(pack.pack_id)

    assert result["report"]["publishable"] is True
    update = coll.update_one.call_args
    assert update.args[0] == {"pack_id": str(pack.pack_id)}
    assert update.args[1]["$set"]["status"] == "published"
    assert "published_at" in update.args[1]["$set"]


@pytest.mark.unit
def test_publish_refuses_unpublishable():
    pack = _pack(KnowledgePackStatus.ARCHIVED)
    client, _ = _mock_mongo()
    completeness = MagicMock(overall_score=0.9, overall_status="complete")
    completeness.categories.model_dump.return_value = {}
    completeness.recommendations = []

    with (
        patch.object(kp, "mongodb_get_knowledge_pack", return_value=pack),
        patch.object(kp, "get_mongodb_client", return_value=client),
        patch("monitor_data.tools.pack_completeness.compute_knowledge_pack_completeness", return_value=completeness),
        pytest.raises(ValueError, match="not publishable"),
    ):
        kp.mongodb_publish_knowledge_pack(pack.pack_id)


@pytest.mark.unit
def test_list_published_filters_on_status():
    listed = MagicMock(packs=["p1", "p2"])
    with patch.object(kp, "mongodb_list_knowledge_packs", return_value=listed) as mock_list:
        out = kp.mongodb_list_published_packs(limit=5000)
    assert out == ["p1", "p2"]
    assert mock_list.call_args.args[0].status == KnowledgePackStatus.PUBLISHED
    assert mock_list.call_args.args[0].limit == 100  # clamped


@pytest.mark.unit
def test_universe_quality_report_gate():
    uid = str(uuid4())
    with (
        patch.object(
            graph_algos,
            "neo4j_universe_connected_components",
            return_value={"universe_id": uid, "orphan_count": 0, "orphans": []},
        ),
        patch.object(graph_algos, "neo4j_universe_node_similarity", return_value=[]),
    ):
        assert graph_algos.neo4j_universe_quality_report(uid)["gate"] == "pass"

    with (
        patch.object(
            graph_algos,
            "neo4j_universe_connected_components",
            return_value={"universe_id": uid, "orphan_count": 2, "orphans": [{"entity_id": "e", "name": "X"}]},
        ),
        patch.object(
            graph_algos,
            "neo4j_universe_node_similarity",
            return_value=[{"entity_a": "a", "entity_b": "b", "similarity": 0.9}],
        ),
    ):
        report = graph_algos.neo4j_universe_quality_report(uid)
        assert report["gate"] == "fail"
        assert report["orphan_count"] == 2
        assert len(report["duplicate_candidates"]) == 1
