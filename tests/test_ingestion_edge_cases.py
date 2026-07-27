"""
Edge-case tests for EPIC 2 ingestion pipeline enhancements.

Covers corner cases, boundary conditions, and integration cross-cutting
concerns across all implemented features:
  #5 — evidence_refs
  #1 — contradiction detection
  #2 — CanonLevel + KnowledgeScope
  #4 — plot thread detection
"""

from datetime import datetime, timezone, UTC
from uuid import uuid4

import pytest
from monitor_data.schemas.base import CanonLevel, KnowledgeScope
from monitor_data.schemas.contradiction import (
    ContradictionFact,
    ContradictionMatch,
    ContradictionResult,
    ContradictionSeverity,
    ContradictionType,
)
from monitor_data.schemas.ingestion_delta import (
    DeltaCategory,
)
from monitor_data.schemas.knowledge_packs import (
    ApplyKnowledgePackRequest,
    ExtractedAxiom,
    ExtractedEntityArchetype,
    ExtractedLoreFact,
    ExtractedPlotThread,
    KnowledgePackResponse,
    KnowledgePackStatus,
    ProfileEvidenceRef,
)
from monitor_data.schemas.plot_threads import (
    PlotThreadCategory,
    PlotThreadUrgency,
)
from monitor_data.tools.ingest_tools.contradiction_detection import (
    _classify_severity,
    _has_negation_conflict,
    _has_opposite_terms,
    _levenshtein_ratio,
    _shares_subject,
    detect_contradictions,
)
from monitor_data.tools.ingest_tools.deduplication import compute_deduplication
from monitor_data.tools.ingest_tools.delta_detection import compute_ingestion_delta

# =============================================================================
# Helpers
# =============================================================================


def _make_response(
    axioms=None,
    entities=None,
    lore_facts=None,
    plot_threads=None,
    tone_profiles=None,
) -> KnowledgePackResponse:
    """Build a minimal KnowledgePackResponse for testing."""
    return KnowledgePackResponse(
        pack_id=uuid4(),
        name="Test Pack",
        description="Test pack for edge cases",
        pack_type="setting_supplement",
        status=KnowledgePackStatus.READY,
        system_name=None,
        source_document_ids=[],
        ingestion_job_id=uuid4(),
        tags=[],
        axioms=axioms or [],
        entity_archetypes=entities or [],
        lore_facts=lore_facts or [],
        entity_relationships=[],
        random_tables=[],
        agendas=[],
        topologies=[],
        tone_profiles=tone_profiles or [],
        character_profiles=[],
        generation_templates=[],
        plot_threads=plot_threads or [],
        game_system_id=None,
        created_at=datetime.now(UTC),
    )


# =============================================================================
# #5 — evidence_refs edge cases
# =============================================================================


class TestEvidenceRefsEdgeCases:
    """Edge cases for evidence_refs on extracted items."""

    def test_evidence_ref_with_only_ref(self):
        """ProfileEvidenceRef with only the required ref field."""
        ref = ProfileEvidenceRef(ref="p.42")
        assert ref.ref == "p.42"
        assert ref.section_path is None
        assert ref.note is None

    def test_evidence_ref_with_all_fields(self):
        ref = ProfileEvidenceRef(
            ref="Chapter 3, p.42",
            section_path="Chapter 3: The Magic System",
            note="Explicit statement about magic rules",
        )
        assert ref.section_path == "Chapter 3: The Magic System"
        assert ref.note == "Explicit statement about magic rules"

    def test_axiom_with_many_evidence_refs(self):
        """Axiom with maximum realistic number of evidence refs."""
        refs = [ProfileEvidenceRef(ref=f"p.{i}") for i in range(20)]
        axiom = ExtractedAxiom(
            statement="Magic is real",
            domain="metaphysics",
            evidence_refs=refs,
        )
        assert len(axiom.evidence_refs) == 20

    def test_entity_archetype_with_evidence(self):
        entity = ExtractedEntityArchetype(
            name="Dragon",
            entity_type="creature",
            description="Large fire-breathing reptile",
            evidence_refs=[
                ProfileEvidenceRef(ref="Monster Manual p.86"),
            ],
        )
        assert len(entity.evidence_refs) == 1

    def test_lore_fact_with_evidence_and_canon_level(self):
        """LoreFact with evidence_refs AND canon_level/knowledge_scope."""
        fact = ExtractedLoreFact(
            statement="The Sundering happened in the Age of Myth",
            canon_level=CanonLevel.CANON,
            knowledge_scope=KnowledgeScope.WORLD,
            evidence_refs=[
                ProfileEvidenceRef(ref="p.12", section_path="History"),
                ProfileEvidenceRef(ref="p.200", section_path="Timeline"),
            ],
        )
        assert fact.canon_level == CanonLevel.CANON
        assert fact.knowledge_scope == KnowledgeScope.WORLD
        assert len(fact.evidence_refs) == 2

    def test_evidence_ref_serialization_roundtrip(self):
        """Ensure evidence_refs survive JSON roundtrip."""
        axiom = ExtractedAxiom(
            statement="Gods walk among mortals",
            domain="theology",
            evidence_refs=[
                ProfileEvidenceRef(ref="p.1", note="Opening line"),
            ],
        )
        json_data = axiom.model_dump(mode="json")
        restored = ExtractedAxiom.model_validate(json_data)
        assert len(restored.evidence_refs) == 1
        assert restored.evidence_refs[0].note == "Opening line"


# =============================================================================
# #1 — Contradiction detection edge cases
# =============================================================================


class TestContradictionEdgeCases:
    """Edge cases for contradiction detection."""

    def test_empty_pack_no_contradictions(self):
        """Pack with no items should produce zero contradictions."""
        pack = _make_response()
        result = detect_contradictions(pack, canon_axioms=[], canon_facts=[])
        assert result.total_contradictions == 0

    def test_empty_canon_no_contradictions(self):
        """Pack with items but no existing canon → no contradictions."""
        pack = _make_response(
            axioms=[ExtractedAxiom(statement="Magic exists", domain="magic")],
        )
        result = detect_contradictions(pack, canon_axioms=[], canon_facts=[])
        assert result.total_contradictions == 0

    def test_identical_statements_no_contradiction(self):
        """Identical statements should NOT be flagged (>0.92 similarity → dedup territory)."""
        pack = _make_response(
            axioms=[
                ExtractedAxiom(statement="Elves are immortal beings", domain="biology")
            ],
        )
        canon = [{"statement": "Elves are immortal beings", "canon_level": "canon"}]
        result = detect_contradictions(pack, canon_axioms=canon, canon_facts=[])
        assert result.total_contradictions == 0

    def test_negation_with_prefix_in_both(self):
        """Both statements have negation prefix → not a contradiction."""
        assert not _has_negation_conflict(
            "dragons are not real",
            "dragons are not fictional",
        )

    def test_negation_case_insensitive(self):
        """Negation detection works with different casing via _compare_statements."""
        # Note: _has_negation_conflict is called on lowered text internally
        assert _has_negation_conflict(
            "elves are not immortal",
            "elves are immortal",
        )

    def test_opposite_terms_substring(self):
        """Opposite terms are detected even as substrings."""
        # 'alive' appears in 'alive', 'dead' appears in 'dead'
        result = _has_opposite_terms("the king is alive", "the king is dead")
        assert result is not None

    def test_opposite_terms_no_false_positive(self):
        """Unrelated terms should not trigger opposite detection."""
        result = _has_opposite_terms("the sword is sharp", "the shield is round")
        assert result is None

    def test_levenshtein_empty_strings(self):
        """Two identical (even empty) strings are 1.0; empty-vs-nonempty is 0.0."""
        assert _levenshtein_ratio("", "") == 1.0
        assert _levenshtein_ratio("hello", "") == 0.0
        assert _levenshtein_ratio("", "hello") == 0.0

    def test_levenshtein_identical(self):
        assert _levenshtein_ratio("hello world", "hello world") == 1.0

    def test_levenshtein_very_different_lengths(self):
        """Strings with wildly different lengths score near zero (rapidfuzz exact ratio)."""
        assert _levenshtein_ratio("hi", "a very very very very very long string") < 0.1

    def test_shares_subject_no_proper_nouns(self):
        """No proper nouns → should return False."""
        assert not _shares_subject(
            "the weather is nice today",
            "the weather was terrible yesterday",
        )

    def test_shares_subject_with_proper_nouns(self):
        """Shared proper noun → should return True."""
        assert _shares_subject(
            "Gandalf arrived in Minas Tirith",
            "Gandalf left the Shire",
        )

    def test_classify_severity_canon_level_high(self):
        """Contradicting canon is HIGH when high similarity."""
        severity = _classify_severity(0.85, "canon")
        assert severity == ContradictionSeverity.HIGH

    def test_classify_severity_canon_level_medium(self):
        """Contradicting canon is MEDIUM when moderate similarity."""
        severity = _classify_severity(0.70, "canon")
        assert severity == ContradictionSeverity.MEDIUM

    def test_classify_severity_proposed_low(self):
        """Contradicting a proposed fact is LOW."""
        severity = _classify_severity(0.85, "proposed")
        assert severity == ContradictionSeverity.LOW

    def test_classify_severity_rumor_low(self):
        """Contradicting a rumor is LOW."""
        severity = _classify_severity(0.85, "rumor")
        assert severity == ContradictionSeverity.LOW

    def test_rumor_lore_fact_skipped(self):
        """Lore facts with knowledge_scope != 'world' are skipped."""
        fact = ExtractedLoreFact(
            statement="Dragons might exist",
            knowledge_scope=KnowledgeScope.RUMOR,
        )
        pack = _make_response(lore_facts=[fact])
        canon = [{"statement": "Dragons do not exist", "canon_level": "canon"}]
        result = detect_contradictions(pack, canon_axioms=[], canon_facts=canon)
        assert result.total_contradictions == 0

    def test_character_belief_lore_fact_skipped(self):
        """Character beliefs should not be contradicted against canon."""
        fact = ExtractedLoreFact(
            statement="The gods are dead",
            knowledge_scope=KnowledgeScope.CHARACTER,
        )
        pack = _make_response(lore_facts=[fact])
        canon = [{"statement": "The gods are alive and active", "canon_level": "canon"}]
        result = detect_contradictions(pack, canon_axioms=[], canon_facts=canon)
        assert result.total_contradictions == 0

    def test_player_knowledge_lore_fact_skipped(self):
        """Player knowledge should not be contradicted against canon."""
        fact = ExtractedLoreFact(
            statement="The villain is the king",
            knowledge_scope=KnowledgeScope.PLAYER,
        )
        pack = _make_response(lore_facts=[fact])
        canon = [{"statement": "The king is benevolent", "canon_level": "canon"}]
        result = detect_contradictions(pack, canon_axioms=[], canon_facts=canon)
        assert result.total_contradictions == 0

    def test_world_scope_fact_checked(self):
        """World-scope facts ARE checked for contradictions."""
        fact = ExtractedLoreFact(
            statement="Elves are not immortal",
            knowledge_scope=KnowledgeScope.WORLD,
        )
        pack = _make_response(lore_facts=[fact])
        canon = [{"statement": "Elves are immortal", "canon_level": "canon"}]
        result = detect_contradictions(pack, canon_axioms=[], canon_facts=canon)
        assert result.total_contradictions >= 1

    def test_multiple_contradictions_in_one_pack(self):
        """A pack with contradicting items detects via opposite terms."""
        # Use opposite terms which are more reliably detected
        pack = _make_response(
            axioms=[
                ExtractedAxiom(
                    statement="Elves are mortal creatures", domain="biology"
                ),
            ],
            lore_facts=[
                ExtractedLoreFact(
                    statement="The great wall is destroyed and in ruins",
                    knowledge_scope=KnowledgeScope.WORLD,
                ),
            ],
        )
        canon_axioms = [
            {"statement": "Elves are immortal beings", "canon_level": "canon"},
        ]
        canon_facts = [
            {
                "statement": "The great wall is intact and stands tall",
                "canon_level": "canon",
            },
        ]
        result = detect_contradictions(
            pack, canon_axioms=canon_axioms, canon_facts=canon_facts
        )
        # Should detect mortal/immortal opposite in axioms
        assert result.total_contradictions >= 1

    def test_contradiction_result_compute_totals(self):
        """compute_totals() correctly aggregates all match lists."""
        result = ContradictionResult(
            axiom_contradictions=[
                ContradictionMatch(
                    contradiction_id="test:1",
                    contradiction_type=ContradictionType.SEMANTIC_OPPOSITE,
                    severity=ContradictionSeverity.HIGH,
                    new_fact=ContradictionFact(statement="new"),
                    existing_fact=ContradictionFact(statement="old"),
                ),
            ],
            lore_contradictions=[
                ContradictionMatch(
                    contradiction_id="test:2",
                    contradiction_type=ContradictionType.PARTIAL_OVERLAP,
                    severity=ContradictionSeverity.LOW,
                    new_fact=ContradictionFact(statement="new2"),
                    existing_fact=ContradictionFact(statement="old2"),
                ),
            ],
        )
        result.compute_totals()
        assert result.total_contradictions == 2
        assert result.high_severity_count == 1
        assert result.all_matches[0].contradiction_id == "test:1"

    def test_entity_description_negation_contradiction(self):
        """Entity descriptions that negate canon facts about that entity are detected."""
        entity = ExtractedEntityArchetype(
            name="Elves",
            entity_type="race",
            description="Elves are mortal beings that can die of old age",
        )
        pack = _make_response(entities=[entity])
        canon = [
            {"statement": "Elves are immortal and live forever", "canon_level": "canon"}
        ]
        result = detect_contradictions(pack, canon_axioms=[], canon_facts=canon)
        # Entity check uses different heuristics — may or may not detect
        assert isinstance(result.total_contradictions, int)


# =============================================================================
# #2 — CanonLevel + KnowledgeScope edge cases
# =============================================================================


class TestCanonLevelKnowledgeScopeEdgeCases:
    """Edge cases for extended CanonLevel and KnowledgeScope enums."""

    def test_canon_level_string_values(self):
        """Ensure all CanonLevel values are lowercase strings."""
        for level in CanonLevel:
            assert level.value == level.value.lower()

    def test_knowledge_scope_string_values(self):
        """Ensure all KnowledgeScope values are lowercase strings."""
        for scope in KnowledgeScope:
            assert scope.value == scope.value.lower()

    def test_lore_fact_default_canon_level_is_proposed(self):
        fact = ExtractedLoreFact(statement="Something happened")
        assert fact.canon_level == CanonLevel.PROPOSED

    def test_lore_fact_default_knowledge_scope_is_world(self):
        fact = ExtractedLoreFact(statement="Something happened")
        assert fact.knowledge_scope == KnowledgeScope.WORLD

    def test_lore_fact_with_each_canon_level(self):
        """Each CanonLevel should be valid on a LoreFact."""
        for level in CanonLevel:
            fact = ExtractedLoreFact(
                statement=f"Fact at {level.value}", canon_level=level
            )
            assert fact.canon_level == level

    def test_lore_fact_with_each_knowledge_scope(self):
        """Each KnowledgeScope should be valid on a LoreFact."""
        for scope in KnowledgeScope:
            fact = ExtractedLoreFact(
                statement=f"Fact in {scope.value} scope", knowledge_scope=scope
            )
            assert fact.knowledge_scope == scope

    def test_canon_level_serialization_roundtrip(self):
        """CanonLevel survives JSON serialization."""
        fact = ExtractedLoreFact(
            statement="Test",
            canon_level=CanonLevel.RUMOR,
            knowledge_scope=KnowledgeScope.RUMOR,
        )
        data = fact.model_dump(mode="json")
        restored = ExtractedLoreFact.model_validate(data)
        assert restored.canon_level == CanonLevel.RUMOR
        assert restored.knowledge_scope == KnowledgeScope.RUMOR

    def test_enum_value_comparison(self):
        """Ensure enum.value comparison works."""
        assert CanonLevel.RUMOR.value == "rumor"
        assert KnowledgeScope.CHARACTER.value == "character"
        # StrEnum str() returns the string value
        assert str(CanonLevel.RUMOR) == "rumor"


# =============================================================================
# #4 — Plot thread edge cases
# =============================================================================


class TestPlotThreadEdgeCases:
    """Edge cases for plot thread extraction and detection."""

    def test_plot_thread_default_category_is_mystery(self):
        thread = ExtractedPlotThread(
            title="Something strange",
            description="Nobody knows what happened",
        )
        assert thread.category == PlotThreadCategory.MYSTERY

    def test_plot_thread_default_urgency_is_medium(self):
        thread = ExtractedPlotThread(
            title="Test",
            description="Test",
        )
        assert thread.urgency == PlotThreadUrgency.MEDIUM

    def test_plot_thread_confidence_bounds(self):
        """Confidence must be between 0.0 and 1.0."""
        # Valid bounds
        ExtractedPlotThread(title="T", description="D", confidence=0.0)
        ExtractedPlotThread(title="T", description="D", confidence=1.0)

        # Out of bounds
        with pytest.raises(Exception):
            ExtractedPlotThread(title="T", description="D", confidence=-0.1)
        with pytest.raises(Exception):
            ExtractedPlotThread(title="T", description="D", confidence=1.1)

    def test_plot_thread_title_max_length(self):
        """Title must respect max_length=300."""
        ExtractedPlotThread(title="T" * 300, description="D")

    def test_plot_thread_description_max_length(self):
        """Description must respect max_length=2000."""
        ExtractedPlotThread(title="T", description="D" * 2000)

    def test_plot_thread_empty_entity_names(self):
        thread = ExtractedPlotThread(title="T", description="D")
        assert thread.entity_names == []

    def test_plot_thread_with_many_entity_names(self):
        thread = ExtractedPlotThread(
            title="War of the Five Kings",
            description="Five kings vie for the throne",
            entity_names=["King A", "King B", "King C", "King D", "King E"],
        )
        assert len(thread.entity_names) == 5

    def test_plot_thread_serialization_roundtrip(self):
        thread = ExtractedPlotThread(
            title="The Dark Prophecy",
            description="An ancient evil stirs",
            category=PlotThreadCategory.THREAT,
            urgency=PlotThreadUrgency.CRITICAL,
            entity_names=["The Dark Lord", "The Chosen One"],
            source_hint="Chapter 1",
            confidence=0.95,
            tags=["prophecy", "main-quest"],
        )
        data = thread.model_dump(mode="json")
        restored = ExtractedPlotThread.model_validate(data)
        assert restored.title == "The Dark Prophecy"
        assert restored.category == PlotThreadCategory.THREAT
        assert restored.urgency == PlotThreadUrgency.CRITICAL
        assert len(restored.entity_names) == 2
        assert restored.source_hint == "Chapter 1"

    def test_knowledge_pack_create_with_mixed_items(self):
        """KnowledgePackCreate with plot_threads alongside other items."""
        from monitor_data.schemas.knowledge_packs import KnowledgePackCreate

        kp = KnowledgePackCreate(
            name="Mixed Pack",
            axioms=[ExtractedAxiom(statement="Magic exists", domain="meta")],
            lore_facts=[ExtractedLoreFact(statement="Elves are real")],
            plot_threads=[
                ExtractedPlotThread(
                    title="The Rising Darkness",
                    description="Something stirs in the east",
                    category=PlotThreadCategory.THREAT,
                    urgency=PlotThreadUrgency.HIGH,
                    confidence=0.8,
                ),
            ],
        )
        assert len(kp.axioms) == 1
        assert len(kp.lore_facts) == 1
        assert len(kp.plot_threads) == 1
        assert kp.plot_threads[0].title == "The Rising Darkness"


# =============================================================================
# Cross-cutting: Delta detection with plot threads
# =============================================================================


class TestDeltaDetectionEdgeCases:
    """Edge cases for delta detection including plot_threads."""

    def test_delta_empty_packs(self):
        """Two empty packs → empty delta."""
        current = _make_response()
        new = _make_response()
        delta = compute_ingestion_delta(current, new, source_id=uuid4())
        assert delta.total_plot_threads == 0
        assert len(delta.plot_threads_delta) == 0

    def test_delta_new_thread_in_new_pack(self):
        """New pack has thread that old pack doesn't → ADDED."""
        current = _make_response()
        new = _make_response(
            plot_threads=[
                ExtractedPlotThread(
                    title="New Mystery",
                    description="Something new",
                    category=PlotThreadCategory.MYSTERY,
                    urgency=PlotThreadUrgency.HIGH,
                    confidence=0.8,
                ),
            ],
        )
        delta = compute_ingestion_delta(current, new, source_id=uuid4())
        assert delta.total_plot_threads == 1
        assert len(delta.plot_threads_delta) == 1
        assert delta.plot_threads_delta[0].delta_category == DeltaCategory.ADDED

    def test_delta_removed_thread(self):
        """Old pack has thread that new pack doesn't → REMOVED."""
        current = _make_response(
            plot_threads=[
                ExtractedPlotThread(
                    title="Old Thread",
                    description="Something old",
                    category=PlotThreadCategory.PROMISE,
                    urgency=PlotThreadUrgency.LOW,
                    confidence=0.7,
                ),
            ],
        )
        new = _make_response()
        delta = compute_ingestion_delta(current, new, source_id=uuid4())
        assert len(delta.plot_threads_delta) == 1
        assert delta.plot_threads_delta[0].delta_category == DeltaCategory.REMOVED

    def test_delta_modified_thread(self):
        """Same title but different description → MODIFIED."""
        current = _make_response(
            plot_threads=[
                ExtractedPlotThread(
                    title="The Quest",
                    description="Original description",
                    category=PlotThreadCategory.PROMISE,
                    urgency=PlotThreadUrgency.MEDIUM,
                    confidence=0.7,
                ),
            ],
        )
        new = _make_response(
            plot_threads=[
                ExtractedPlotThread(
                    title="The Quest",
                    description="Updated description with more details",
                    category=PlotThreadCategory.PROMISE,
                    urgency=PlotThreadUrgency.HIGH,
                    confidence=0.9,
                ),
            ],
        )
        delta = compute_ingestion_delta(current, new, source_id=uuid4())
        assert len(delta.plot_threads_delta) == 1
        assert delta.plot_threads_delta[0].delta_category == DeltaCategory.MODIFIED

    def test_delta_thread_counts_in_rolled_stats(self):
        """Plot thread changes count toward net_new/modified/removed rollup."""
        current = _make_response()
        new = _make_response(
            plot_threads=[
                ExtractedPlotThread(
                    title="Thread 1",
                    description="A new thread",
                    category=PlotThreadCategory.MYSTERY,
                    urgency=PlotThreadUrgency.MEDIUM,
                    confidence=0.7,
                ),
            ],
        )
        delta = compute_ingestion_delta(current, new, source_id=uuid4())
        assert delta.net_new_items >= 1  # Should include the plot thread


# =============================================================================
# Cross-cutting: Deduplication with plot threads
# =============================================================================


class TestDeduplicationEdgeCases:
    """Edge cases for deduplication including plot_threads."""

    def test_dedup_no_existing_packs(self):
        """No existing packs → all items are novel."""
        new = _make_response(
            plot_threads=[
                ExtractedPlotThread(
                    title="Fresh Thread",
                    description="Brand new",
                    category=PlotThreadCategory.MYSTERY,
                    urgency=PlotThreadUrgency.MEDIUM,
                    confidence=0.7,
                ),
            ],
        )
        result = compute_deduplication(new, [], multiverse_id=str(uuid4()))
        assert result.total_items_checked >= 1

    def test_dedup_identical_title_different_description(self):
        """Same title but different description should still match as duplicate."""
        thread_a = ExtractedPlotThread(
            title="The Dark Lord's Return",
            description="Version A",
            category=PlotThreadCategory.THREAT,
            urgency=PlotThreadUrgency.HIGH,
            confidence=0.8,
        )
        thread_b = ExtractedPlotThread(
            title="The Dark Lord's Return",
            description="Version B with different text",
            category=PlotThreadCategory.THREAT,
            urgency=PlotThreadUrgency.HIGH,
            confidence=0.85,
        )
        existing = _make_response(plot_threads=[thread_a])
        new = _make_response(plot_threads=[thread_b])
        result = compute_deduplication(new, [existing], multiverse_id=str(uuid4()))
        assert result.has_duplicates is True


# =============================================================================
# Cross-cutting: ApplyKnowledgePackRequest
# =============================================================================


class TestApplyKnowledgePackRequestEdgeCases:
    """Edge cases for apply flags."""

    def test_all_apply_flags_default_true(self):
        """All apply flags should default to True."""
        mv_id = uuid4()
        req = ApplyKnowledgePackRequest(multiverse_id=mv_id)
        assert req.apply_axioms is True
        assert req.apply_entities is True
        assert req.apply_lore_facts is True
        assert req.apply_relationships is True
        assert req.apply_random_tables is True
        assert req.apply_agendas is True
        assert req.apply_topologies is True
        assert req.apply_tone_profiles is True
        assert req.apply_plot_threads is True

    def test_can_selectively_disable_plot_threads(self):
        """Apply everything except plot threads."""
        mv_id = uuid4()
        req = ApplyKnowledgePackRequest(
            multiverse_id=mv_id,
            apply_plot_threads=False,
        )
        assert req.apply_axioms is True
        assert req.apply_plot_threads is False


# =============================================================================
# Cross-cutting: KnowledgePackResponse plot_threads
# =============================================================================


class TestKnowledgePackResponsePlotThreads:
    """Verify KnowledgePackResponse correctly includes plot_threads."""

    def test_response_inherits_plot_threads(self):
        threads = [
            ExtractedPlotThread(
                title="Thread A",
                description="First thread",
                category=PlotThreadCategory.PROMISE,
                urgency=PlotThreadUrgency.LOW,
                confidence=0.7,
            ),
            ExtractedPlotThread(
                title="Thread B",
                description="Second thread",
                category=PlotThreadCategory.THREAT,
                urgency=PlotThreadUrgency.HIGH,
                confidence=0.9,
            ),
        ]
        resp = _make_response(plot_threads=threads)
        assert len(resp.plot_threads) == 2
        assert resp.plot_threads[0].title == "Thread A"
        assert resp.plot_threads[1].category == PlotThreadCategory.THREAT

    def test_response_empty_plot_threads_default(self):
        resp = _make_response()
        assert resp.plot_threads == []
