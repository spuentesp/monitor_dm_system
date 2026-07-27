"""Contract tests for the KnowledgePack completeness schemas.

Verifies that pack_completeness Pydantic models:
- instantiate with valid data,
- enforce required fields,
- enforce numeric / length constraints.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from monitor_data.schemas.pack_completeness import (
    CompletenessCategory,
    CompletenessScores,
    KnowledgePackCompleteness,
)
from pydantic import ValidationError

pytestmark = pytest.mark.unit


# =============================================================================
# CompletenessCategory
# =============================================================================


class TestCompletenessCategory:
    def test_minimal(self):
        c = CompletenessCategory(
            category="axioms",
            present=5,
            expected=10,
            score=0.5,
            status="partial",
        )
        assert c.category == "axioms"
        assert c.present == 5
        assert c.expected == 10
        assert c.score == 0.5
        assert c.status == "partial"

    def test_complete(self):
        c = CompletenessCategory(
            category="entities", present=42, expected=42, score=1.0, status="complete"
        )
        assert c.score == 1.0
        assert c.status == "complete"

    def test_missing(self):
        c = CompletenessCategory(
            category="agendas", present=0, expected=5, score=0.0, status="missing"
        )
        assert c.score == 0.0
        assert c.status == "missing"

    def test_required_fields(self):
        with pytest.raises(ValidationError):
            CompletenessCategory()  # type: ignore[call-arg]

    def test_required_status(self):
        with pytest.raises(ValidationError):
            CompletenessCategory(category="x", present=0, expected=0, score=0.0)  # type: ignore[call-arg]


# =============================================================================
# CompletenessScores
# =============================================================================


class TestCompletenessScores:
    def _category(self, name: str, score: float, status: str = "complete"):
        return CompletenessCategory(
            category=name, present=10, expected=10, score=score, status=status
        )

    def test_all_complete(self):
        s = CompletenessScores(
            axioms=self._category("axioms", 1.0),
            entities=self._category("entities", 1.0),
            lore=self._category("lore", 1.0),
            tables=self._category("tables", 1.0),
            agendas=self._category("agendas", 1.0),
            game_system=self._category("game_system", 1.0),
            topologies=self._category("topologies", 1.0),
        )
        assert s.axioms.score == 1.0
        assert s.game_system.score == 1.0

    def test_mixed_scores(self):
        s = CompletenessScores(
            axioms=self._category("axioms", 1.0),
            entities=self._category("entities", 0.5, status="partial"),
            lore=self._category("lore", 0.0, status="missing"),
            tables=self._category("tables", 1.0),
            agendas=self._category("agendas", 1.0),
            game_system=self._category("game_system", 1.0),
            topologies=self._category("topologies", 1.0),
        )
        assert s.entities.status == "partial"
        assert s.lore.status == "missing"

    def test_required_all_seven(self):
        # All 7 sub-categories are required
        with pytest.raises(ValidationError):
            CompletenessScores(axioms=self._category("axioms", 1.0))  # type: ignore[call-arg]


# =============================================================================
# KnowledgePackCompleteness
# =============================================================================


class TestKnowledgePackCompleteness:
    def _scores(self):
        return CompletenessScores(
            axioms=CompletenessCategory(
                category="axioms", present=10, expected=10, score=1.0, status="complete"
            ),
            entities=CompletenessCategory(
                category="entities",
                present=10,
                expected=10,
                score=1.0,
                status="complete",
            ),
            lore=CompletenessCategory(
                category="lore", present=10, expected=10, score=1.0, status="complete"
            ),
            tables=CompletenessCategory(
                category="tables", present=10, expected=10, score=1.0, status="complete"
            ),
            agendas=CompletenessCategory(
                category="agendas",
                present=10,
                expected=10,
                score=1.0,
                status="complete",
            ),
            game_system=CompletenessCategory(
                category="game_system",
                present=10,
                expected=10,
                score=1.0,
                status="complete",
            ),
            topologies=CompletenessCategory(
                category="topologies",
                present=10,
                expected=10,
                score=1.0,
                status="complete",
            ),
        )

    def test_minimal(self):
        c = KnowledgePackCompleteness(
            pack_id=uuid4(),
            pack_name="PF2e Core",
            pack_type="rulebook",
            overall_score=0.85,
            overall_status="partial",
            categories=self._scores(),
            summary="85% complete — missing random tables",
        )
        assert c.pack_name == "PF2e Core"
        assert c.overall_score == 0.85
        assert c.overall_status == "partial"
        assert c.missing_categories == []
        assert c.partial_categories == []
        assert c.thresholds_applied == {}
        assert c.recommendations == []

    def test_full(self):
        c = KnowledgePackCompleteness(
            pack_id=uuid4(),
            pack_name="Curse of Strahd",
            pack_type="adventure_module",
            overall_score=0.62,
            overall_status="partial",
            categories=self._scores(),
            missing_categories=["random_tables"],
            partial_categories=["entities"],
            summary="62% complete — missing random tables",
            thresholds_applied={"axioms": 100, "entities": 50},
            recommendations=["Add more random tables"],
        )
        assert "random_tables" in c.missing_categories
        assert "entities" in c.partial_categories
        assert c.thresholds_applied["axioms"] == 100

    def test_overall_score_min(self):
        with pytest.raises(ValidationError):
            KnowledgePackCompleteness(
                pack_id=uuid4(),
                pack_name="x",
                pack_type="x",
                overall_score=-0.01,
                overall_status="empty",
                categories=self._scores(),
                summary="x",
            )

    def test_overall_score_max(self):
        with pytest.raises(ValidationError):
            KnowledgePackCompleteness(
                pack_id=uuid4(),
                pack_name="x",
                pack_type="x",
                overall_score=1.01,
                overall_status="complete",
                categories=self._scores(),
                summary="x",
            )

    def test_overall_score_bounds(self):
        c_min = KnowledgePackCompleteness(
            pack_id=uuid4(),
            pack_name="x",
            pack_type="x",
            overall_score=0.0,
            overall_status="empty",
            categories=self._scores(),
            summary="x",
        )
        c_max = KnowledgePackCompleteness(
            pack_id=uuid4(),
            pack_name="x",
            pack_type="x",
            overall_score=1.0,
            overall_status="complete",
            categories=self._scores(),
            summary="x",
        )
        assert c_min.overall_score == 0.0
        assert c_max.overall_score == 1.0

    def test_summary_too_long(self):
        with pytest.raises(ValidationError):
            KnowledgePackCompleteness(
                pack_id=uuid4(),
                pack_name="x",
                pack_type="x",
                overall_score=0.5,
                overall_status="partial",
                categories=self._scores(),
                summary="x" * 501,
            )

    def test_required_pack_id(self):
        with pytest.raises(ValidationError):
            KnowledgePackCompleteness(
                pack_name="x",
                pack_type="x",
                overall_score=0.5,
                overall_status="partial",
                categories=self._scores(),
                summary="x",
            )

    def test_required_pack_name(self):
        with pytest.raises(ValidationError):
            KnowledgePackCompleteness(
                pack_id=uuid4(),
                pack_type="x",
                overall_score=0.5,
                overall_status="partial",
                categories=self._scores(),
                summary="x",
            )

    def test_required_pack_type(self):
        with pytest.raises(ValidationError):
            KnowledgePackCompleteness(
                pack_id=uuid4(),
                pack_name="x",
                overall_score=0.5,
                overall_status="partial",
                categories=self._scores(),
                summary="x",
            )

    def test_required_overall_score(self):
        with pytest.raises(ValidationError):
            KnowledgePackCompleteness(
                pack_id=uuid4(),
                pack_name="x",
                pack_type="x",
                overall_status="partial",
                categories=self._scores(),
                summary="x",
            )

    def test_required_overall_status(self):
        with pytest.raises(ValidationError):
            KnowledgePackCompleteness(
                pack_id=uuid4(),
                pack_name="x",
                pack_type="x",
                overall_score=0.5,
                categories=self._scores(),
                summary="x",
            )

    def test_required_categories(self):
        with pytest.raises(ValidationError):
            KnowledgePackCompleteness(
                pack_id=uuid4(),
                pack_name="x",
                pack_type="x",
                overall_score=0.5,
                overall_status="partial",
                summary="x",
            )

    def test_required_summary(self):
        with pytest.raises(ValidationError):
            KnowledgePackCompleteness(
                pack_id=uuid4(),
                pack_name="x",
                pack_type="x",
                overall_score=0.5,
                overall_status="partial",
                categories=self._scores(),
            )
